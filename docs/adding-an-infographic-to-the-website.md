# Adding an Infographic to the Website

Once you have a finished HTML infographic, follow these steps to publish it on the SME&C Infographic Hub. Everything is done through the GitHub website — no command-line tools required.

## 1. Navigate to the Correct Category Folder

Go to the repository on GitHub and open the folder that matches your infographic's topic:

| Folder | Category |
|---|---|
| `azure-sql/` | Azure SQL |
| `fabric/` | Fabric |
| `foundry/` | Foundry |
| `github-copilot/` | GitHub Copilot |
| `avd/` | AVD |
| `app-platform-services/` | App Platform Services |
| `azure-openai/` | Azure OpenAI |
| `defender-for-cloud/` | Defender for Cloud |

Click on the folder name to open it.

## 2. Upload Your HTML File

1. In the category folder, click the **Add file** button (top-right) and select **Upload files**
2. Drag your `.html` file onto the upload area, or click **choose your files** to browse for it
3. Make sure the file name uses kebab-case (e.g., `sql-migration-guide.html`)

## 3. Create a Branch and Propose the Change

Below the upload area you'll see a commit section:

1. Add a short description like *"Add SQL migration guide infographic"*
2. Select **Create a new branch for this commit and start a pull request**
3. Give the branch a descriptive name (e.g., `add-sql-migration-guide`)
4. Click **Propose changes**

## 4. Open the Pull Request

GitHub will take you to the pull request form:

1. Add any extra details in the description if helpful
2. Click **Create pull request**

Once a maintainer reviews and merges your PR, the website will automatically update and your infographic will appear on the site.

## That's It!

You only need to upload the HTML file to the right folder and open a PR. The manifest and site are updated automatically when your PR is merged.
