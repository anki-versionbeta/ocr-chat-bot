import { NextResponse } from "next/server";

/**
 * API route to generate and download a sample Excel template for HBR target list
 */
export async function GET() {
  try {
    // Create a simple CSV format for the sample template with three columns
    // This can be opened in Excel and will have the proper structure
    const csvContent = `Parameter,Search_Pages,Comments
Residual Product A,"12,13,14","Look in table header"
Residual Product B,"25,26","Check calculation section"
Residual Product C,38,"Bottom of page"
Residual Product D,"45,47,48","Found in equipment cleaning section"
Residual Product E,"52,53","May be listed as 'Product E Residual'"

Note: Replace the sample data above with your actual parameters, search pages, and comments.
You can add more rows as needed.`;

    // Return the CSV file
    return new NextResponse(csvContent, {
      status: 200,
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition":
          "attachment; filename=hbr_target_list_template.csv",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        Pragma: "no-cache",
        Expires: "0",
      },
    });
  } catch (error) {
    console.error("Error generating sample template:", error);
    return NextResponse.json(
      { error: "Failed to generate sample template" },
      { status: 500 }
    );
  }
}
