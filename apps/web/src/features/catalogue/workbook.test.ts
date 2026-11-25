import { describe, expect, it } from "vitest";
import {
  IMPORT_MODES,
  OFFLINE_MESSAGE,
  canCommitReport,
  exportPath,
  importModeLabel,
  workbookFileProblem,
  type WorkbookReport,
} from "./workbook";

describe("catalogue workbook actions", () => {
  it("names each import mode", () => {
    expect(IMPORT_MODES.map((mode) => importModeLabel(mode.id))).toEqual([
      "Create new records only",
      "Update matching existing records",
      "Create new and update matching records",
    ]);
  });

  it("keeps an offline import from writing", () => {
    expect(OFFLINE_MESSAGE).toContain("Nothing was changed.");
  });

  it("accepts only an xlsx file within the size limit", () => {
    expect(workbookFileProblem("menu.csv", 100)).toBe("Choose an .xlsx workbook.");
    expect(workbookFileProblem("menu.xlsx", 0)).toBe("The workbook is empty.");
    expect(workbookFileProblem("menu.xlsx", 10 * 1024 * 1024 + 1)).toBe("The workbook is larger than 10 MB.");
    expect(workbookFileProblem("menu.xlsx", 20)).toBeNull();
  });

  it("exports the current search when one is typed", () => {
    expect(exportPath("  ")).toBe("/api/v1/catalogue/workbook/export");
    expect(exportPath("Daal")).toBe("/api/v1/catalogue/workbook/export?q=Daal");
  });

  it("blocks confirmation while any row failed", () => {
    const report = { failed: 1 } as WorkbookReport;
    expect(canCommitReport(report)).toBe(false);
    expect(canCommitReport({ ...report, failed: 0 })).toBe(true);
  });
});
