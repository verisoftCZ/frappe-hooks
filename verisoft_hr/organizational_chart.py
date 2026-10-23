import frappe
from frappe import _
from frappe.query_builder.functions import Count


@frappe.whitelist()
def get_children(
    parent: str | None = None,
    company: str | None = None,
    exclude_node: str | None = None,
):
    if frappe.session.user == "Guest" or not frappe.has_permission(
        "Employee", "read"
    ):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    filters = [["status", "=", "Active"]]

    if company and company != "All Companies":
        filters.append(["company", "=", company])

    if parent and company and parent != company:
        filters.append(["reports_to", "=", parent])
    else:
        filters.append(["reports_to", "=", ""])

    if exclude_node:
        filters.append(["name", "!=", exclude_node])

    employees = frappe.get_all(
        "Employee",
        fields=[
            "employee_name as name",
            "name as id",
            "lft",
            "rgt",
            "reports_to",
            "image",
            "designation as title",
        ],
        filters=filters,
        order_by="name",
    )

    Employee = frappe.qb.DocType("Employee")

    for employee in employees:
        result = (
            frappe.qb.from_(Employee)
            .select(Count(Employee.name))
            .where(
                (Employee.lft > employee.lft)
                & (Employee.rgt < employee.rgt)
                & (Employee.status == "Active")
            )
        ).run()

        employee.connections = result[0][0]
        employee.expandable = bool(employee.connections)

        employee.pop("lft", None)
        employee.pop("rgt", None)

    return employees
