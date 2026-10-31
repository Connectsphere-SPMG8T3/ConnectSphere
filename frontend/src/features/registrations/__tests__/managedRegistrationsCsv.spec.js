import { describe, expect, it } from "vitest";

import {
  buildManagedRegistrationsCsv,
  managedRegistrationStatusLabel,
} from "../managedRegistrationsCsv";

describe("managed registration CSV export", () => {
  it("uses only the fields allowed for the manager's active role", () => {
    const registrations = [
      {
        full_name: "Priya Nair",
        email: "priya@example.test",
        phone_number: "+65 8000 0001",
        status: "registered",
      },
    ];

    const organiserCsv = buildManagedRegistrationsCsv(registrations, false);
    const coordinatorCsv = buildManagedRegistrationsCsv(registrations, true);

    expect(organiserCsv).toBe('\uFEFF"Full name","Status"\r\n"Priya Nair","Registered"');
    expect(organiserCsv).not.toContain("priya@example.test");
    expect(organiserCsv).not.toContain("+65 8000 0001");
    expect(coordinatorCsv).toBe(
      '\uFEFF"Full name","Email","Phone","Status"\r\n"Priya Nair","priya@example.test","\'+65 8000 0001","Registered"',
    );
  });

  it("escapes CSV syntax and prevents spreadsheet formula interpretation", () => {
    const csv = buildManagedRegistrationsCsv(
      [{
        full_name: '=SUM("A1")',
        email: 'alex,"tan"@example.test',
        phone_number: null,
        status: "withdrawn",
      }],
      true,
    );

    expect(csv).toBe(
      '\uFEFF"Full name","Email","Phone","Status"\r\n"\'=SUM(""A1"")","alex,""tan""@example.test","","Withdrawn"',
    );
  });

  it("labels only the manager-facing registration statuses", () => {
    expect(["registered", "waitlisted", "invited", "withdrawn"].map(managedRegistrationStatusLabel)).toEqual([
      "Registered",
      "Waitlisted",
      "Invited",
      "Withdrawn",
    ]);
  });
});
