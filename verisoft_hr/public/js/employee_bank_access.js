// The server filters the actual values. This only mirrors document-level access
// in Desk, whose normal field permissions are calculated from static roles.
frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new()) return;
		const access = frm.doc.__onload?.verisoft_bank_access;
		frm.perm[2] = {
			...(frm.perm[2] || {}),
			read: access?.read === 1 ? 1 : 0,
			write: access?.write === 1 ? 1 : 0,
		};
		frm.refresh_fields();
	},
});
