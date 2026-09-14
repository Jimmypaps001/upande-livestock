import { call, type Envelope } from "@/lib/frappe";

const EMPLOYEES = "upande_livestock.serverscripts.people.employee_options.employee_options";

export interface EmployeeChoice {
  value: string;
  label: string;
  detail: string;
}

export interface EmployeeSearch {
  employees: EmployeeChoice[];
  /** The Employee linked to whoever is signed in, or null. */
  mine: string | null;
  query: string;
  more: boolean;
}

/** Employees matching what has been typed, by name or by number. */
export function searchEmployees(q = ""): Promise<Envelope<EmployeeSearch>> {
  return call<EmployeeSearch>(EMPLOYEES, { payload: { q } });
}
