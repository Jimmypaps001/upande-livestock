// Consolidated from the "Milking Palour Checksheet" Client Script fixture (doctype_js hook).

frappe.ui.form.on("Milking Palour Checksheet", {
    equipment: function(frm) {
        // clear old items
        frm.clear_table("inspection_items");

        // get items for selected equipment
        const equipment = frm.doc.equipment;
        const parameters = get_parameters_for_equipment(equipment);

        parameters.forEach(param => {
            const row = frm.add_child("inspection_items");
            row.equipment = equipment;
            row.part_name = param;          // fill part_name
            row.parameter_checked = param;  // also fill parameter_checked
            row.status = "Not Checked";
            row.notes = "";
        });

        frm.refresh_field("inspection_items");
    }
});


function get_parameters_for_equipment(equipment) {
    const mapping = {
        "VACUUM PUMP CYLINDER": [
            "CLEANING",
            "PRESSURE GAUGE",
            "OIL LEVEL",
            "LOOSE CONNECTION",
            "DAMAGED/ LEAKING PIPES",
            "LEAKAGES/ OIL SPILLS",
            "V.BELT",
            "MOTOR OVERHEATING",
            "EXHAUST LEAKAGES",
            "BREEDER",
            "ELECTRICAL PANELS",
            "LIGHTS",
            "AIR CLEANER"
        ],
        "MILKING PARLOR": [
            "CLUSTERS",
            "LIGHTS",
            "MILK METER GAUGE",
            "MILK PUMP SWITCH",
            "DIAPHRAGMS",
            "LINNERS SYSTEM",
            "MILK LEVEL SENSOR",
            "MILK COLLECTING TANK",
            "PARLOR GATES",
            "P.GATES SWITCHES",
            "P.GATES SPRING",
            "PALOR LADDERS",
            "DISPLAY CABINETS",
            "TAG SENSOR",
            "MILK LINES",
            "FILTER LINE",
            "BARREL GLASS",
            "MILK PUMPS",
            "PULLING ROPES"
        ],
        "COOLING TANKS": [
            "AGITATORS",
            "MOTORS",
            "BREATHERS",
            "DISPLAY UNIT",
            "SPRAY BALLS",
            "COMPRESSORS",
            "CONTROL BOARD",
            "ELECTRICAL PANELS"
        ],
        "MOBILE SCALE": [
            "CALIBRATION",
            "DISPLAY",
            "CHARGING",
            "STABILITY"
        ],
        "FIREWOOD BOILER": [
            "WATER SUPPLY AND LEVEL",
            "BLOWER",
            "RECYCLING PUMP",
            "ELECTRICAL PANEL",
            "PRESSURE GAUGE",
            "TEMPERATURE GAUGE",
            "DIGITAL CONTROL BOARD"
        ]
    };

    return mapping[equipment] || [];
}
