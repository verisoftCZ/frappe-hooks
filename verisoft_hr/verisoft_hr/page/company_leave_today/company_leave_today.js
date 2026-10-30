frappe.pages["company-leave-today"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Nepřítomnosti dnes - všichni zaměstnanci"),
		single_column: true,
	});
	const content = $('<div class="p-4"></div>').appendTo(page.main);
	let request = 0;

	async function refresh() {
		const current = ++request;
		// Clear previous data immediately, including when a refresh fails.
		content.empty().append($('<p class="text-muted"></p>').text(__("Načítání…")));
		try {
			const response = await frappe.call({ method: "verisoft_hr.company_leave_today.get_today_leaves" });
			if (current !== request) return;
			const data = response.message;
			content.empty();
			$('<p class="text-muted"></p>')
				.text(`${data.company} · ${frappe.datetime.str_to_user(data.date)} · ${data.employees.length}`)
				.appendTo(content);
			if (!data.employees.length) {
				$("<p></p>").text(__("Dnes nejsou evidovány žádné schválené nepřítomnosti.")).appendTo(content);
				return;
			}
			const container = $('<div class="table-responsive"></div>').appendTo(content);
			const table = $('<table class="table table-bordered"></table>').appendTo(container);
			const header = $("<tr></tr>").appendTo($("<thead></thead>").appendTo(table));
			[__("Zaměstnanec"), __("Oddělení"), __("Rozsah dnes")].forEach((label) => {
				$('<th scope="col"></th>').text(label).appendTo(header);
			});
			const body = $("<tbody></tbody>").appendTo(table);
			data.employees.forEach((employee) => {
				const row = $("<tr></tr>").appendTo(body);
				[
					employee.employee_name,
					employee.department || "—",
					employee.half_day ? __("Půl dne") : __("Celý den"),
				].forEach((value) => $("<td></td>").text(value).appendTo(row));
			});
		} catch (error) {
			if (current !== request) return;
			content.empty().append(
				$('<p class="text-danger" role="alert"></p>').text(__("Přehled se nepodařilo načíst."))
			);
		}
	}
	page.set_primary_action(__("Obnovit"), refresh, "refresh");
	wrapper.refresh_company_leaves = refresh;
};

frappe.pages["company-leave-today"].on_page_show = function (wrapper) {
	wrapper.refresh_company_leaves();
};
