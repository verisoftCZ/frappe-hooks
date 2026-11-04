import frappe

CURRENT_FIELDS = {
    "current_mobile_number": "cell_number",
    "current_personal_email": "personal_email",
    "current_date_of_birth": "date_of_birth",
    "current_address": "current_address",
    "current_permanent_address": "permanent_address",
    "current_bank_ac_no": "bank_ac_no",
}
NEW_FIELDS = {
    "new_mobile_number": "cell_number",
    "new_personal_email": "personal_email",
    "new_date_of_birth": "date_of_birth",
    "new_address": "current_address",  # Keep the existing fieldname and historical requests.
    "new_permanent_address": "permanent_address",
    "new_bank_ac_no": "bank_ac_no",
}


@frappe.whitelist()
def get_request_defaults(employee=None):
    """Permission-checked form defaults; ordinary users can only load themselves."""
    user = frappe.session.user
    roles = frappe.get_roles()
    if user == "Guest" or not {"Employee", "HR User", "HR Manager"}.intersection(roles):
        frappe.throw("Not permitted to request employee data changes.", frappe.PermissionError)
    own_employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    is_hr = bool({"HR User", "HR Manager"}.intersection(roles))
    if employee and employee != own_employee and not is_hr:
        frappe.throw("You can only request changes to your own employee record.", frappe.PermissionError)
    employee = employee or own_employee
    if not employee:
        frappe.throw("No Employee record is linked to the current user.")
    record = frappe.get_doc("Employee", employee)
    record.check_permission("read")
    record.apply_fieldlevel_read_permissions()
    values = {target: record.get(source) for target, source in CURRENT_FIELDS.items()}
    values.update(employee=record.name, requested_by=user, request_date=frappe.utils.now())
    return {"values": values, "bank_access": {"read": 1, "write": 1}}


def validate_request(doc, method=None):
    user = frappe.session.user
    roles = frappe.get_roles(user)

    is_hr = "HR Manager" in roles or "HR User" in roles

    if is_hr:
        if not doc.employee:
            frappe.throw("Employee is required.")

        employee = frappe.db.get_value(
            "Employee",
            doc.employee,
            [
                "name",
                "cell_number",
                "personal_email",
                "date_of_birth",
                "current_address",
                "permanent_address",
                "bank_ac_no",
            ],
            as_dict=True,
        )

        if not employee:
            frappe.throw("Employee not found.")

    else:
        employee = frappe.db.get_value(
            "Employee",
            {"user_id": user},
            [
                "name",
                "cell_number",
                "personal_email",
                "date_of_birth",
                "current_address",
                "permanent_address",
                "bank_ac_no",
            ],
            as_dict=True,
        )

        if not employee:
            frappe.throw("No Employee record is linked to the current user.")

        if not doc.is_new():
            stored_employee = frappe.db.get_value(doc.doctype, doc.name, "employee")
            if stored_employee != employee.name:
                frappe.throw("You can only change your own employee request.", frappe.PermissionError)
        doc.employee = employee.name

    doc.requested_by = user

    if doc.is_new():
        doc.request_date = frappe.utils.now()

    for target, source in CURRENT_FIELDS.items():
        doc.set(target, employee.get(source))


def apply_approved_changes(doc, method=None):
    if doc.workflow_state != "Approved":
        return

    if doc.changes_applied:
        return

    employee = frappe.get_doc("Employee", doc.employee)

    for source, target in NEW_FIELDS.items():
        if doc.get(source):
            employee.set(target, doc.get(source))

    employee.save(ignore_permissions=True)

    doc.db_set("changes_applied", 1)
