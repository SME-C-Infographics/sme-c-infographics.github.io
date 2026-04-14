# Creating HTML Infographics with CoWork

This guide walks you through using CoWork to generate a self-contained HTML infographic for the SME&C Infographic Hub.

## Prerequisites

- Access to CoWork
- A clear topic or presentation you want to turn into an infographic

## Steps

### 1. Start a CoWork Session

Open CoWork and begin a new session. Give it context about the infographic you need — for example, the Azure service, the key concepts, and the target audience.

### 2. Prompt for an Infographic

Ask CoWork to generate a single-file HTML infographic. A good prompt includes:

- **Topic** — the service or concept to visualize
- **Key points** — the 3–6 most important takeaways
- **Style** — request it follow the Microsoft Fluent / Segoe UI style to stay consistent with the rest of the site

> **Example prompt:**
> "Create a single-file HTML infographic about Azure SQL Managed Instance migration paths. Include sections for assessment, migration options, and post-migration validation. Use Microsoft Fluent design with Segoe UI font."

### 3. Review and Refine

CoWork will produce an HTML file with inline CSS and SVG graphics. Review it by:

1. Saving the output as an `.html` file
2. Opening it in your browser to verify layout and content
3. Iterating with CoWork if anything needs adjustment (e.g., "make the comparison table wider" or "add a section on pricing")

### 4. Finalise the File

Before committing, make sure the file:

- Is **fully self-contained** — all styles, scripts, and images are inline (no external dependencies)
- Has a descriptive file name using kebab-case (e.g., `sql-2016-eol-customer-guide.html`)
- Renders correctly at common screen widths (desktop and tablet)

## Tips

- Keep infographics focused — one topic per file works best.
- Use CoWork's iteration loop to polish layout and copy before committing.
- If you need icons or diagrams, ask CoWork to embed them as inline SVGs.

## Next Steps

Once your HTML file is ready, follow [Adding an Infographic to the Website](adding-an-infographic-to-the-website.md) to publish it.
