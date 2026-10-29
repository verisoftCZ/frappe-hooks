const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../verisoft_hr");
let count = 0;
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (file.endsWith(".json")) {
      JSON.parse(fs.readFileSync(file, "utf8"));
      count++;
    }
  }
}
walk(root);
const expected = {
  workflow: ["Employee Data Change Request Approval", "Employee leave request workflow"],
  client_script: ["Employee Data Change Request Script", "Leave Application - HR Only Leave Types"],
  workflow_action_master: ["Submit Request", "Submit & Approve", "Register", "Review", "Reject", "Approve"],
};
for (const [fixture, names] of Object.entries(expected)) {
  const records = JSON.parse(fs.readFileSync(path.join(root, "fixtures", `${fixture}.json`), "utf8"));
  assert.deepEqual(records.map(record => record.name).sort(), [...names].sort(), `Unexpected records in ${fixture}`);
}
console.log(`OK: ${count} JSON files parsed; fixture record names match the handoff.`);
