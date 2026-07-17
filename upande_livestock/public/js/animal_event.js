// Animal Event form scripts — consolidated from enabled Client Script fixtures.
// (The disabled 'Dynainamic fields on Animal event' script is intentionally omitted.)

/* ================= Animal Event controller ================= */
// =============================================================
// ANIMAL EVENT CONTROLLER — v2.0
// Consolidated client script for all 12 event types
// Reads validation thresholds from Livestock Settings (Single)
// =============================================================

let LIVESTOCK_SETTINGS = null;

function load_livestock_settings(callback) {
    if (LIVESTOCK_SETTINGS) {
        callback(LIVESTOCK_SETTINGS);
        return;
    }
    frappe.call({
        method: "frappe.client.get",
        args: { doctype: "Livestock Settings", name: "Livestock Settings" },
        async: false,
        callback: function(r) {
            LIVESTOCK_SETTINGS = r.message || {};
            callback(LIVESTOCK_SETTINGS);
        }
    });
}

// ── Helper: get animal age in months ──
function get_animal_age_months(frm, callback) {
    if (!frm.doc.animal) { callback(null); return; }
    frappe.call({
        method: "frappe.client.get_value",
        args: { doctype: "Animal", filters: { name: frm.doc.animal }, fieldname: ["date_of_birth", "sex"] },
        async: false,
        callback: function(r) {
            if (r.message && r.message.date_of_birth) {
                let birth = frappe.datetime.str_to_obj(r.message.date_of_birth);
                let now = frappe.datetime.str_to_obj(frappe.datetime.get_today());
                let months = (now.getFullYear() - birth.getFullYear()) * 12 + (now.getMonth() - birth.getMonth());
                callback({ age_months: months, sex: r.message.sex });
            } else {
                callback({ age_months: null, sex: null });
            }
        }
    });
}


frappe.ui.form.on("Animal Event", {

    event_type: function(frm) {
        toggle_event_fields(frm);

        // Initialize Service with Pending status
        if (frm.doc.event_type === "Service" && !frm.doc.pregnancy_confirmation_status) {
            frm.set_value("pregnancy_confirmation_status", "Pending");
        }
        // Auto-set event_date to today for all events that use it
        if (frm.doc.event_type && !frm.doc.event_date) {
            frm.set_value("event_date", frappe.datetime.get_today());
        }
    },

    refresh: function(frm) {
        toggle_event_fields(frm);

        // Cache settings on form load
        load_livestock_settings(function() {});

        // Filter: related_service → only submitted Service events for this animal
        frm.set_query("related_service", function() {
            return { filters: { animal: frm.doc.animal, event_type: "Service", docstatus: 1 } };
        });

        // Filter: animal → only livestock assets
        frm.set_query("animal", function() {
            return { filters: {} };
        });

        // Filter: related pregnancy → only submitted Service events for this animal
        frm.set_query("custom_related_pregnancy", function() {
            return { filters: { animal: frm.doc.animal, event_type: "Service", docstatus: 1 } };
        });
    },

    pregnancy_confirmation_status: function(frm) {
        if (frm.doc.pregnancy_confirmation_status === "Confirmed") {
            frm.set_df_property("pregnancy_confirmation_date", "hidden", 0);
            if (!frm.doc.pregnancy_confirmation_date) {
                frm.set_value("pregnancy_confirmation_date", frappe.datetime.get_today());
            }
            frm.set_value("service_status", "Successfull");
        } else {
            frm.set_df_property("pregnancy_confirmation_date", "hidden", 1);
            if (["Not Pregnant", "Aborted"].includes(frm.doc.pregnancy_confirmation_status)) {
                frm.set_value("service_status", "Failed");
            }
        }
    },

    diagnosis_result: function(frm) {
        if (frm.doc.event_type === "Pregnancy Diagnosis" && frm.doc.related_service) {
            update_service_status(frm);
        }
    },

    // ============================================================
    // VALIDATE — runs before save, does all business rule checks
    // ============================================================
    validate: function(frm) {
        let et = frm.doc.event_type;
        let isMovement    = (et === "Movement");
        let isService     = (et === "Service");
        let isDiagnosis   = (et === "Pregnancy Diagnosis");
        let isCalving     = (et === "Calving");
        let isBirth       = (et === "Birth");
        let isDryingOff   = (et === "Drying Off");
        let isVaccination = (et === "Vaccination");
        let isDeworming   = (et === "Deworming");
        let isDehorning   = (et === "Dehorning");
        let isHoofTrim    = (et === "Hoof Trimming");
        let isWeight      = (et === "Weight Recording");
        let isHeat        = (et === "Heat Detection");

        // Husbandry group: Vaccination, Deworming, Dehorning, Hoof Trimming
        let isHusbandry = isVaccination || isDeworming || isDehorning || isHoofTrim;

        load_livestock_settings(function(settings) {

            // ── 1. PREGNANCY DIAGNOSIS ──
            if (isDiagnosis) {
                if (!frm.doc.related_service) {
                    frappe.throw("You must select a Related Service before recording Pregnancy Diagnosis.");
                }
                frappe.call({
                    method: "frappe.client.get",
                    args: { doctype: "Animal Event", name: frm.doc.related_service },
                    async: false,
                    callback: function(r) {
                        if (!r.message) {
                            frappe.throw("Selected Service event not found.");
                        } else if (frm.doc.diagnosis_date && frm.doc.diagnosis_date < r.message.service_date) {
                            frappe.throw("Diagnosis Date cannot be before Service Date (" + r.message.service_date + ").");
                        }
                    }
                });
            }

            // ── 2. SERVICE ──
            if (isService) {
                // Age check
                get_animal_age_months(frm, function(info) {
                    if (info && info.age_months !== null) {
                        let min_age = settings.min_service_age_months || 15;
                        if (info.age_months < min_age) {
                            frappe.throw("This animal is " + info.age_months + " months old. Minimum age for service is " + min_age + " months. Update in Livestock Settings if needed.");
                        }
                    }
                });

                // Check active pregnancy
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: "Pregnancy Diagnosis", diagnosis_result: "Confirmed", docstatus: 1 },
                        fields: ["name", "diagnosis_date", "related_service"],
                        order_by: "diagnosis_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0) {
                            let pregnancy = r.message[0];
                            frappe.call({
                                method: "frappe.client.get_list",
                                args: {
                                    doctype: "Animal Event",
                                    filters: { animal: frm.doc.animal, event_type: "Calving", custom_related_pregnancy: pregnancy.related_service, docstatus: 1 },
                                    fields: ["name"]
                                },
                                async: false,
                                callback: function(cr) {
                                    if (!cr.message || cr.message.length === 0) {
                                        frappe.throw("Cannot record Service: this animal has an active confirmed pregnancy.");
                                    }
                                }
                            });
                        }
                    }
                });

                if (!frm.doc.pregnancy_confirmation_status) {
                    frm.set_value("pregnancy_confirmation_status", "Pending");
                }
            }

            // ── 3. CALVING ──
            if (isCalving) {
                if (!frm.doc.custom_related_pregnancy) {
                    frappe.throw("You must link this Calving to a Service/Pregnancy event.");
                }
                // Age check
                get_animal_age_months(frm, function(info) {
                    if (info && info.age_months !== null) {
                        let min_age = settings.min_calving_age_months || 24;
                        if (info.age_months < min_age) {
                            frappe.throw("This animal is " + info.age_months + " months old. Minimum calving age is " + min_age + " months.");
                        }
                    }
                });
                // Minimum interval between calvings
                let min_interval = settings.min_calving_interval_days || 270;
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: "Calving", docstatus: 1, name: ["!=", frm.doc.name || ""] },
                        fields: ["name", "event_date"],
                        order_by: "event_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0 && r.message[0].event_date && frm.doc.event_date) {
                            let last = frappe.datetime.str_to_obj(r.message[0].event_date);
                            let now  = frappe.datetime.str_to_obj(frm.doc.event_date);
                            let diff = frappe.datetime.get_diff(now, last);
                            if (diff < min_interval) {
                                frappe.throw("Last calving was " + diff + " days ago. Minimum interval is " + min_interval + " days.");
                            }
                        }
                    }
                });
            }

            // ── 4. BIRTH (similar to Calving for the dam) ──
            if (isBirth) {
                let min_interval = settings.min_calving_interval_days || 270;
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: ["in", ["Birth", "Calving"]], docstatus: 1, name: ["!=", frm.doc.name || ""] },
                        fields: ["name", "event_date"],
                        order_by: "event_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0 && r.message[0].event_date && frm.doc.event_date) {
                            let diff = frappe.datetime.get_diff(frm.doc.event_date, r.message[0].event_date);
                            if (diff < min_interval) {
                                frappe.throw("Last birth/calving was " + diff + " days ago. Minimum interval is " + min_interval + " days.");
                            }
                        }
                    }
                });
            }

            // ── 5. DEHORNING — age window ──
            if (isDehorning) {
                get_animal_age_months(frm, function(info) {
                    if (info && info.age_months !== null) {
                        let min_m = settings.min_dehorning_age_months || 1;
                        let max_m = settings.max_dehorning_age_months || 6;
                        if (info.age_months < min_m || info.age_months > max_m) {
                            frappe.throw("Dehorning age window is " + min_m + "-" + max_m + " months. This animal is " + info.age_months + " months.");
                        }
                    }
                });
            }

            // ── 6. VACCINATION — minimum interval check ──
            if (isVaccination) {
                let min_days = settings.min_vaccination_interval_days || 21;
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: "Vaccination", docstatus: 1, name: ["!=", frm.doc.name || ""] },
                        fields: ["name", "event_date", "custom_vaccine_drug_name"],
                        order_by: "event_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0 && r.message[0].event_date && frm.doc.event_date) {
                            let diff = frappe.datetime.get_diff(frm.doc.event_date, r.message[0].event_date);
                            if (diff < min_days && frm.doc.custom_vaccine_drug_name === r.message[0].custom_vaccine_drug_name) {
                                frappe.throw("Same vaccine was given " + diff + " days ago. Minimum interval is " + min_days + " days.");
                            }
                        }
                    }
                });
            }

            // ── 7. DEWORMING — minimum interval check ──
            if (isDeworming) {
                let min_days = settings.min_deworming_interval_days || 90;
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: "Deworming", docstatus: 1, name: ["!=", frm.doc.name || ""] },
                        fields: ["name", "event_date"],
                        order_by: "event_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0 && r.message[0].event_date && frm.doc.event_date) {
                            let diff = frappe.datetime.get_diff(frm.doc.event_date, r.message[0].event_date);
                            if (diff < min_days) {
                                frappe.throw("Last deworming was " + diff + " days ago. Minimum interval is " + min_days + " days.");
                            }
                        }
                    }
                });
            }

            // ── 8. HOOF TRIMMING — minimum interval ──
            if (isHoofTrim) {
                let min_days = settings.min_hoof_trimming_interval_days || 90;
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: "Hoof Trimming", docstatus: 1, name: ["!=", frm.doc.name || ""] },
                        fields: ["name", "event_date"],
                        order_by: "event_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0 && r.message[0].event_date && frm.doc.event_date) {
                            let diff = frappe.datetime.get_diff(frm.doc.event_date, r.message[0].event_date);
                            if (diff < min_days) {
                                frappe.throw("Last hoof trimming was " + diff + " days ago. Minimum interval is " + min_days + " days.");
                            }
                        }
                    }
                });
            }

            // ── 9. WEIGHT RECORDING — minimum interval ──
            if (isWeight) {
                let min_days = settings.min_weight_recording_interval_days || 7;
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Animal Event",
                        filters: { animal: frm.doc.animal, event_type: "Weight Recording", docstatus: 1, name: ["!=", frm.doc.name || ""] },
                        fields: ["name", "event_date"],
                        order_by: "event_date desc", limit: 1
                    },
                    async: false,
                    callback: function(r) {
                        if (r.message && r.message.length > 0 && r.message[0].event_date && frm.doc.event_date) {
                            let diff = frappe.datetime.get_diff(frm.doc.event_date, r.message[0].event_date);
                            if (diff < min_days) {
                                frappe.throw("Last weight recording was " + diff + " days ago. Minimum interval is " + min_days + " days.");
                            }
                        }
                    }
                });
                // Weight must be positive
                if (frm.doc.custom_weight && frm.doc.custom_weight <= 0) {
                    frappe.throw("Weight must be a positive number.");
                }
            }

        }); // end load_livestock_settings

        // ============================================================
        // CLEAR IRRELEVANT FIELDS based on event type
        // ============================================================
        // Movement fields
        if (!isMovement) {
            frm.set_value("current_herd", null);
            frm.set_value("new_herd", null);
        }
        // Service fields
        if (!isService) {
            frm.set_value("sire", null);
            frm.set_value("service_type", null);
            frm.set_value("service_date", null);
            frm.set_value("service_status", null);
            frm.set_value("pregnancy_confirmation_status", null);
            frm.set_value("pregnancy_confirmation_date", null);
        }
        // Diagnosis fields
        if (!isDiagnosis) {
            frm.set_value("diagnosis_date", null);
            frm.set_value("diagnosis_result", null);
            frm.set_value("diagnosis_remarks", null);
            frm.set_value("related_service", null);
        }
        // Calving fields
        if (!isCalving && !isBirth) {
            frm.set_value("custom_calving_outcome", null);
            frm.set_value("custom_no_of_calves", null);
            frm.set_value("custom_calf_sex", null);
        }
        if (!isCalving) {
            frm.set_value("custom_related_pregnancy", null);
        }
        // Husbandry fields — clear if not a husbandry/dehorning type
        if (!isHusbandry && !isVaccination && !isDeworming) {
            frm.set_value("custom_vaccine_drug_name", null);
            frm.set_value("custom_dosage", null);
            frm.set_value("custom_batch_no", null);
            frm.set_value("custom_withdrawal_period_days", null);
            frm.set_value("custom_next_due_date", null);
        }
        // Weight — clear if not weight recording
        if (!isWeight) {
            frm.set_value("custom_weight", null);
        }
    }
});


// ==================================================================
// TOGGLE FIELD VISIBILITY based on event_type selection
// ==================================================================
function toggle_event_fields(frm) {
    let et = frm.doc.event_type;
    let isMovement    = (et === "Movement");
    let isService     = (et === "Service");
    let isDiagnosis   = (et === "Pregnancy Diagnosis");
    let isCalving     = (et === "Calving");
    let isBirth       = (et === "Birth");
    let isDryingOff   = (et === "Drying Off");
    let isVaccination = (et === "Vaccination");
    let isDeworming   = (et === "Deworming");
    let isDehorning   = (et === "Dehorning");
    let isHoofTrim    = (et === "Hoof Trimming");
    let isWeight      = (et === "Weight Recording");
    let isHeat        = (et === "Heat Detection");

    // Group flags
    let needsDrug     = isVaccination || isDeworming || isDehorning;
    let needsCalvInfo = isCalving || isBirth;

    // ── event_date: visible for ALL event types ──
    frm.set_df_property("event_date", "hidden", 0);
    frm.set_df_property("event_date", "reqd", 1);
    frm.set_df_property("event_date", "label", isService ? "Service Date" : isMovement ? "Movement Date" : isDiagnosis ? "Diagnosis Date" : "Event Date");

    // ── Movement fields ──
    frm.set_df_property("current_herd", "hidden", !isMovement);
    frm.set_df_property("current_herd", "reqd", isMovement);
    frm.set_df_property("new_herd", "hidden", !isMovement);
    frm.set_df_property("new_herd", "reqd", isMovement);

    // ── Service fields ──
    frm.set_df_property("sire", "hidden", !isService);
    frm.set_df_property("sire", "reqd", isService);
    frm.set_df_property("service_type", "hidden", !isService);
    frm.set_df_property("service_type", "reqd", isService);
    frm.set_df_property("service_date", "hidden", !isService);
    frm.set_df_property("service_date", "reqd", isService);
    frm.set_df_property("service_status", "hidden", !isService);
    frm.set_df_property("pregnancy_confirmation_status", "hidden", !isService);
    frm.set_df_property("custom_status_after_test", "hidden", !isService);
    if (frm.doc.pregnancy_confirmation_status === "Confirmed" && isService) {
        frm.set_df_property("pregnancy_confirmation_date", "hidden", 0);
    } else {
        frm.set_df_property("pregnancy_confirmation_date", "hidden", 1);
    }

    // ── Pregnancy Diagnosis fields ──
    frm.set_df_property("diagnosis_date", "hidden", !isDiagnosis);
    frm.set_df_property("diagnosis_date", "reqd", isDiagnosis);
    frm.set_df_property("diagnosis_result", "hidden", !isDiagnosis);
    frm.set_df_property("diagnosis_result", "reqd", isDiagnosis);
    frm.set_df_property("diagnosis_remarks", "hidden", !isDiagnosis);
    frm.set_df_property("related_service", "hidden", !isDiagnosis);
    frm.set_df_property("related_service", "reqd", isDiagnosis);

    // ── Calving / Birth fields ──
    frm.set_df_property("custom_calving_outcome", "hidden", !needsCalvInfo);
    frm.set_df_property("custom_calving_outcome", "reqd", needsCalvInfo);
    frm.set_df_property("custom_no_of_calves", "hidden", !needsCalvInfo);
    frm.set_df_property("custom_calf_sex", "hidden", !needsCalvInfo);
    frm.set_df_property("custom_related_pregnancy", "hidden", !isCalving);
    frm.set_df_property("custom_related_pregnancy", "reqd", isCalving);

    // ── Vaccine / Drug fields (Vaccination, Deworming, Dehorning) ──
    frm.set_df_property("custom_vaccine_drug_name", "hidden", !needsDrug);
    frm.set_df_property("custom_vaccine_drug_name", "reqd", isVaccination || isDeworming);
    frm.set_df_property("custom_vaccine_drug_name", "label", isDehorning ? "Method / Tool" : "Vaccine / Drug Name");
    frm.set_df_property("custom_dosage", "hidden", !(isVaccination || isDeworming));
    frm.set_df_property("custom_dosage", "reqd", isVaccination || isDeworming);
    frm.set_df_property("custom_batch_no", "hidden", !(isVaccination || isDeworming));
    frm.set_df_property("custom_withdrawal_period_days", "hidden", !(isVaccination || isDeworming));
    frm.set_df_property("custom_next_due_date", "hidden", !(isVaccination || isDeworming || isHoofTrim));

    // ── Weight field ──
    frm.set_df_property("custom_weight", "hidden", !isWeight);
    frm.set_df_property("custom_weight", "reqd", isWeight);

    // ── Activity cost — visible for husbandry events ──
    let showCost = needsDrug || isHoofTrim || isWeight || isHeat || isDryingOff;
    frm.set_df_property("custom_activity_cost", "hidden", !showCost);

    // ── Remarks — always visible ──
    frm.set_df_property("remarks", "hidden", 0);
}


// ==================================================================
// UPDATE SERVICE STATUS from Pregnancy Diagnosis result
// ==================================================================
function update_service_status(frm) {
    if (frm.doc.diagnosis_result === "Confirmed") {
        frappe.call({
            method: "frappe.client.set_value",
            args: {
                doctype: "Animal Event",
                name: frm.doc.related_service,
                fieldname: { pregnancy_confirmation_status: "Confirmed", service_status: "Successfull", pregnancy_confirmation_date: frm.doc.diagnosis_date }
            },
            callback: function(r) {
                if (r.message) {
                    frappe.show_alert({ message: __("Related Service updated to Confirmed"), indicator: "green" }, 3);
                }
            }
        });
    } else if (["Not Pregnant", "Aborted"].includes(frm.doc.diagnosis_result)) {
        frappe.call({
            method: "frappe.client.set_value",
            args: {
                doctype: "Animal Event",
                name: frm.doc.related_service,
                fieldname: { pregnancy_confirmation_status: frm.doc.diagnosis_result, service_status: "Failed" }
            },
            callback: function(r) {
                if (r.message) {
                    frappe.show_alert({ message: __("Related Service updated to Failed"), indicator: "orange" }, 3);
                }
            }
        });
    }
}

/* ================= Control on Animal events ================= */
frappe.ui.form.on("Animal Event", {
    event_type: function(frm) {
        toggle_event_fields(frm);

        // When Service is first created, set pregnancy status = Pending
        if (frm.doc.event_type === "Service" && !frm.doc.pregnancy_confirmation_status) {
            frm.set_value("pregnancy_confirmation_status", "Pending");
        }
    },

    refresh: function(frm) {
        toggle_event_fields(frm);

        // --- Filter related_service dropdown only for Diagnosis ---
        frm.set_query("related_service", function() {
            return {
                filters: {
                    animal: frm.doc.animal,
                    event_type: "Service",
                    docstatus: 1
                }
            };
        });
    },

    pregnancy_confirmation_status: function(frm) {
        // Show pregnancy confirmation date only if confirmed
        if (frm.doc.pregnancy_confirmation_status === "Confirmed") {
            frm.set_df_property("pregnancy_confirmation_date", "hidden", 0);
            frm.set_value("service_status", "Successfull");   // ✅ Correct spelling
        } else {
            frm.set_df_property("pregnancy_confirmation_date", "hidden", 1);

            if (["Not Pregnant", "Aborted"].includes(frm.doc.pregnancy_confirmation_status)) {
                frm.set_value("service_status", "Failed");
            }
        }
    },

    validate: function(frm) {
        let isMovement   = (frm.doc.event_type === "Movement");
        let isService    = (frm.doc.event_type === "Service");
        let isDiagnosis  = (frm.doc.event_type === "Pregnancy Diagnosis");

        // ----------------------------
        // 1. Block invalid Pregnancy Diagnosis
        // ----------------------------
        if (isDiagnosis) {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Animal Event",
                    filters: {
                        animal: frm.doc.animal,
                        event_type: "Service",
                        docstatus: 1
                    },
                    fields: ["name", "service_date"],
                    order_by: "service_date desc",
                    limit: 1
                },
                async: false,
                callback: function(r) {
                    if (!r.message || r.message.length === 0) {
                        frappe.throw("⚠️ Cannot record Pregnancy Diagnosis: this animal has no Service event.");
                    } else {
                        let last_service = r.message[0];
                        if (frm.doc.diagnosis_date && frm.doc.diagnosis_date < last_service.service_date) {
                            frappe.throw("⚠️ Diagnosis Date cannot be before the last Service Date (" + last_service.service_date + ").");
                        }
                    }
                }
            });
        }

        // ----------------------------
        // 2. Block Service if animal already pregnant
        // ----------------------------
        if (isService) {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Animal Event",
                    filters: {
                        animal: frm.doc.animal,
                        event_type: "Pregnancy Diagnosis",
                        diagnosis_result: "Confirmed",
                        docstatus: 1
                    },
                    fields: ["name", "diagnosis_date"],
                    order_by: "diagnosis_date desc",
                    limit: 1
                },
                async: false,
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        frappe.throw("⚠️ Cannot record Service: this animal already has a Confirmed Pregnancy.");
                    }
                }
            });

            // Ensure new Service always starts with Pending pregnancy status
            if (!frm.doc.pregnancy_confirmation_status) {
                frm.set_value("pregnancy_confirmation_status", "Pending");
            }
        }

        // ----------------------------
        // 3. Clear irrelevant fields
        // ----------------------------
        if (!isMovement) {
            frm.set_value("current_herd", null);
            frm.set_value("new_herd", null);
            frm.set_value("event_date", null);
        }
        if (!isService) {
            frm.set_value("sire", null);
            frm.set_value("service_type", null);
            frm.set_value("service_date", null);
            frm.set_value("service_status", null);
            frm.set_value("pregnancy_confirmation_status", null);
            frm.set_value("pregnancy_confirmation_date", null);
        }
        if (!isDiagnosis) {
            frm.set_value("diagnosis_date", null);
            frm.set_value("diagnosis_result", null);
            frm.set_value("diagnosis_remarks", null);
            frm.set_value("related_service", null);
        }
    }
});


function toggle_event_fields(frm) {
    let isMovement   = (frm.doc.event_type === "Movement");
    let isService    = (frm.doc.event_type === "Service");
    let isDiagnosis  = (frm.doc.event_type === "Pregnancy Diagnosis");

    // --- Movement fields ---
    frm.set_df_property("current_herd", "hidden", !isMovement);
    frm.set_df_property("current_herd", "reqd", isMovement);

    frm.set_df_property("new_herd", "hidden", !isMovement);
    frm.set_df_property("new_herd", "reqd", isMovement);

    frm.set_df_property("event_date", "hidden", !isMovement);
    frm.set_df_property("event_date", "reqd", isMovement);

    // --- Service fields ---
    frm.set_df_property("sire", "hidden", !isService);
    frm.set_df_property("sire", "reqd", isService);

    frm.set_df_property("service_type", "hidden", !isService);
    frm.set_df_property("service_type", "reqd", isService);

    frm.set_df_property("service_date", "hidden", !isService);
    frm.set_df_property("service_date", "reqd", isService);

    frm.set_df_property("service_status", "hidden", !isService);
    frm.set_df_property("service_status", "reqd", isService);

    frm.set_df_property("pregnancy_confirmation_status", "hidden", !isService);
    frm.set_df_property("pregnancy_confirmation_status", "reqd", isService);

    // Pregnancy confirmation date only if confirmed
    if (frm.doc.pregnancy_confirmation_status === "Confirmed" && isService) {
        frm.set_df_property("pregnancy_confirmation_date", "hidden", 0);
    } else {
        frm.set_df_property("pregnancy_confirmation_date", "hidden", 1);
    }

    // --- Diagnosis fields ---
    frm.set_df_property("diagnosis_date", "hidden", !isDiagnosis);
    frm.set_df_property("diagnosis_date", "reqd", isDiagnosis);

    frm.set_df_property("diagnosis_result", "hidden", !isDiagnosis);
    frm.set_df_property("diagnosis_result", "reqd", isDiagnosis);

    frm.set_df_property("diagnosis_remarks", "hidden", !isDiagnosis);

    frm.set_df_property("related_service", "hidden", !isDiagnosis);
    frm.set_df_property("related_service", "reqd", isDiagnosis);
}


/* ================= Test on dynamic pregnancy ================= */
frappe.ui.form.on("Animal Event", {
    event_type: function(frm) {
        toggle_event_fields(frm);

        // When Service is first created, set pregnancy status = Pending
        if (frm.doc.event_type === "Service" && !frm.doc.pregnancy_confirmation_status) {
            frm.set_value("pregnancy_confirmation_status", "Pending");
        }
    },

    refresh: function(frm) {
        toggle_event_fields(frm);

        // --- Filter related_service dropdown only for Diagnosis ---
        frm.set_query("related_service", function() {
            return {
                filters: {
                    animal: frm.doc.animal,
                    event_type: "Service",
                    docstatus: 1
                }
            };
        });
    },

    pregnancy_confirmation_status: function(frm) {
        // Show pregnancy confirmation date only if confirmed
        if (frm.doc.pregnancy_confirmation_status === "Confirmed") {
            frm.set_df_property("pregnancy_confirmation_date", "hidden", 0);

            // auto–set today's date if missing
            if (!frm.doc.pregnancy_confirmation_date) {
                frm.set_value("pregnancy_confirmation_date", frappe.datetime.get_today());
            }

            frm.set_value("service_status", "Successfull");  // matches field option spelling
        } else {
            frm.set_df_property("pregnancy_confirmation_date", "hidden", 1);

            if (["Not Pregnant", "Aborted"].includes(frm.doc.pregnancy_confirmation_status)) {
                frm.set_value("service_status", "Failed");
            }
        }
    },

    // Clear irrelevant values + sanity checks
    validate: function(frm) {
        let isMovement   = (frm.doc.event_type === "Movement");
        let isService    = (frm.doc.event_type === "Service");
        let isDiagnosis  = (frm.doc.event_type === "Pregnancy Diagnosis");

        // If not Movement, clear movement fields
        if (!isMovement) {
            frm.set_value("current_herd", null);
            frm.set_value("new_herd", null);
            frm.set_value("event_date", null);
        }

        // If not Service, clear service fields
        if (!isService) {
            frm.set_value("sire", null);
            frm.set_value("service_type", null);
            frm.set_value("service_date", null);
            frm.set_value("service_status", null);
            frm.set_value("pregnancy_confirmation_status", null);
            frm.set_value("pregnancy_confirmation_date", null);
        } else {
            // Ensure service-created docs have a Pending pregnancy status
            if (!frm.doc.pregnancy_confirmation_status) {
                frm.set_value("pregnancy_confirmation_status", "Pending");
            }
        }

        // If not Diagnosis, clear diagnosis fields
        if (!isDiagnosis) {
            frm.set_value("diagnosis_date", null);
            frm.set_value("diagnosis_result", null);
            frm.set_value("diagnosis_remarks", null);
            frm.set_value("related_service", null);
        }

        // ---- Additional sanity checks ----

        // Disallow diagnosis without related service
        if (isDiagnosis && !frm.doc.related_service) {
            frappe.throw("You must select the Related Service before recording Pregnancy Diagnosis.");
        }

        // Disallow new Service if a successful one already exists
        if (isService && frm.doc.animal) {
            frappe.call({
                method: "frappe.client.get_list",
                async: false,   // block save until check completes
                args: {
                    doctype: "Animal Event",
                    filters: {
                        animal: frm.doc.animal,
                        event_type: "Service",
                        service_status: "Successfull",
                        docstatus: 1
                    },
                    fields: ["name"]
                },
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        frappe.throw("This animal already has a successful service. Cannot add a new one.");
                    }
                }
            });
        }
    }
});


function toggle_event_fields(frm) {
    let isMovement   = (frm.doc.event_type === "Movement");
    let isService    = (frm.doc.event_type === "Service");
    let isDiagnosis  = (frm.doc.event_type === "Pregnancy Diagnosis");

    // --- Movement fields ---
    frm.set_df_property("current_herd", "hidden", !isMovement);
    frm.set_df_property("current_herd", "reqd", isMovement);

    frm.set_df_property("new_herd", "hidden", !isMovement);
    frm.set_df_property("new_herd", "reqd", isMovement);

    frm.set_df_property("event_date", "hidden", !isMovement);
    frm.set_df_property("event_date", "reqd", isMovement);

    // --- Service fields ---
    frm.set_df_property("sire", "hidden", !isService);
    frm.set_df_property("sire", "reqd", isService);

    frm.set_df_property("service_type", "hidden", !isService);
    frm.set_df_property("service_type", "reqd", isService);

    frm.set_df_property("service_date", "hidden", !isService);
    frm.set_df_property("service_date", "reqd", isService);

    frm.set_df_property("service_status", "hidden", !isService);
    frm.set_df_property("service_status", "reqd", isService);

    frm.set_df_property("pregnancy_confirmation_status", "hidden", !isService);
    frm.set_df_property("pregnancy_confirmation_status", "reqd", isService);

    // Pregnancy confirmation date should stay hidden unless confirmed
    if (frm.doc.pregnancy_confirmation_status === "Confirmed" && isService) {
        frm.set_df_property("pregnancy_confirmation_date", "hidden", 0);
    } else {
        frm.set_df_property("pregnancy_confirmation_date", "hidden", 1);
    }

    // --- Pregnancy Diagnosis fields ---
    frm.set_df_property("diagnosis_date", "hidden", !isDiagnosis);
    frm.set_df_property("diagnosis_date", "reqd", isDiagnosis);

    frm.set_df_property("diagnosis_result", "hidden", !isDiagnosis);
    frm.set_df_property("diagnosis_result", "reqd", isDiagnosis);

    frm.set_df_property("diagnosis_remarks", "hidden", !isDiagnosis);

    frm.set_df_property("related_service", "hidden", !isDiagnosis);
    frm.set_df_property("related_service", "reqd", isDiagnosis);
}

