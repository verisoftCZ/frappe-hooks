import frappe


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
            ],
            as_dict=True,
        )

        if not employee:
            frappe.throw("No Employee record is linked to the current user.")

        doc.employee = employee.name

    doc.requested_by = user

    if doc.is_new():
        doc.request_date = frappe.utils.now()

    doc.current_mobile_number = employee.cell_number
    doc.current_personal_email = employee.personal_email
    doc.current_date_of_birth = employee.date_of_birth
    doc.current_address = employee.current_address


def apply_approved_changes(doc, method=None):
    if doc.workflow_state != "Approved":
        return

    if doc.changes_applied:
        return

    employee = frappe.get_doc("Employee", doc.employee)

    if doc.new_mobile_number:
        employee.cell_number = doc.new_mobile_number

    if doc.new_personal_email:
        employee.personal_email = doc.new_personal_email

    if doc.new_date_of_birth:
        employee.date_of_birth = doc.new_date_of_birth

    if doc.new_address:
        employee.current_address = doc.new_address

    employee.save(ignore_permissions=True)

    doc.db_set("changes_applied", 1)
