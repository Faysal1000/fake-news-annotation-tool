# Fake News Dataset Annotator

A standalone GUI tool for collecting a multimodal fake news detection dataset. Multiple annotators can use this tool to enter news text, attach images and video, classify entries as Fake or Real, and specify the type of fake news. All data is saved in a structured CSV file with images stored locally.

**No coding knowledge required** — download a single file, double-click, and start annotating.

<br>
<p align="center">
  <img src="annotator/assets/annotate_mode.png" alt="Fake News Annotator - Annotate Mode" width="600">
</p>
<p align="center">
  <img src="annotator/assets/review_mode.png" alt="Fake News Annotator - Review Mode" width="380">
  <img src="annotator/assets/re-label_mode.png" alt="Fake News Annotator - Re-label Mode" width="380">
</p>

---

## Quick Start

Go to the [**Releases**](../../releases/latest) page and download the file for your operating system:

| File                                       | Platform                     |
| ------------------------------------------ | ---------------------------- |
| `FakeNewsAnnotator-Windows.exe`            | Windows 10/11 (64-bit)       |
| `FakeNewsAnnotator-macOS-AppleSilicon.zip` | macOS (Apple M1/M2/M3/M4/M5) |
| `FakeNewsAnnotator-Linux`                  | Ubuntu / Debian / Fedora     |

### Installation Instructions

**1. Windows**: Open Command Prompt (`cmd`) and paste this to automatically create a folder on your Desktop and download it there:
```cmd
mkdir "%USERPROFILE%\Desktop\Fake News Dataset" 2>nul & cd "%USERPROFILE%\Desktop\Fake News Dataset" & curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-Windows.exe
```

**2. macOS (Apple Silicon)**: Open **Terminal** and paste the exact command below. This will download the app, extract it, and automatically bypass Gatekeeper's quarantine warning so you can just double-click to open it:
```bash
mkdir -p ~/Desktop/"Fake News Dataset" && cd ~/Desktop/"Fake News Dataset" && curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-macOS-AppleSilicon.zip && unzip -o FakeNewsAnnotator-macOS-AppleSilicon.zip && rm FakeNewsAnnotator-macOS-AppleSilicon.zip
```
*(If you download the .zip manually, put the extracted `FakeNewsAnnotator.app` into a folder on your Desktop named `Fake News Dataset`, open Terminal and run `chmod -R +x ~/Desktop/"Fake News Dataset"/FakeNewsAnnotator.app && xattr -cr ~/Desktop/"Fake News Dataset"/FakeNewsAnnotator.app`)*

**3. Linux**: Open your terminal and paste this command to download it and make it executable:
```bash
mkdir -p ~/Desktop/"Fake News Dataset" && cd ~/Desktop/"Fake News Dataset" && curl -L -O https://github.com/Faysal1000/fake-news-annotation-tool/releases/latest/download/FakeNewsAnnotator-Linux && chmod +x FakeNewsAnnotator-Linux
```

---

## Core Features

You can switch between the app's three primary modes using the dropdown switcher at the top left of the screen:

- **Annotate Mode**: Add new entries to the dataset. Select labels, add text, drag-and-drop media, and save.
- **Review Mode**: Browse through your saved annotations. You can edit mistakes, delete entries, and view attached media in full resolution.
- **Re-label Mode**: Conduct inter-rater reliability tests. Browse a pre-generated sample of records with the previous labels hidden to prevent bias.
- **📊 Detailed Stats**: Click the button at the top to open a comprehensive, interactive dashboard. Click row/column headers to dynamically calculate multi-modal distribution percentages.

---

## Data Management

All data is generated locally. The tool will automatically create `dataset.csv`, `images/` and `videos/` folders, and a config file **in the same folder** where the executable is located.

### Dataset Output Format
The `dataset.csv` file automatically records:
- A unique `id` and `timestamp` for safe merging.
- Your `annotator` name and `annotation_confidence`.
- The `label` (Fake/Real) and `multi_category` (Misinformation/Satire/Clickbait).
- The `heading`, body `text`, and the platform `source_category`.
- The exact relative paths to any saved media (`image_path`, `video_path`).

The tool also maintains a `non_duplicates.json` file which safely stores any pairs of news articles you manually marked as "Non Duplicate" during duplicate auditing so they don't get flagged again.

- **Submitting Data**: When you are done annotating, send your `dataset.csv`, `non_duplicates.json`, and your `images/` and `videos/` folders to your project lead.
- **Aggregating Data**: Project leads can combine work from multiple annotators. Put everyone's folders into one master folder, open the Annotator Tool, click **"Scripts"** (top right), and select **"Aggregate Datasets"**. The script will automatically merge both the dataset records and the marked non-duplicates list seamlessly.

---

## Advanced Features

- **Team Sync**: You can sync your local metrics to the cloud using a GitHub Gist so your entire team can view each other's progress in real-time. Setup instructions are inside the app's "Detailed Stats -> Team Sync" menu.
- **Inter-Rater Reliability (Kappa Testing)**: You can extract a balanced random sample of records from your master `dataset.csv` right from the tool's **Scripts** menu. Distribute this sample to your team for blind re-labeling, and calculate the Kappa score automatically.
- **Telegram Bot Integration**: This project includes a built-in Telegram bot (located in the `bot-server/` directory) to easily route news links to assigned annotators. See the bot directory for setup details. 

---

## For Developers

```bash
# Clone the repository
git clone https://github.com/Faysal1000/fake-news-annotation-tool.git
cd fake-news-annotation-tool

# Enable local Git hooks (prevents pushing mismatched version tags)
git config core.hooksPath .githooks

cd annotator

# Install dependencies
pip install -r requirements.txt

# Run the tool
python annotator_tool.py
```

### GitHub Actions CI/CD
The project includes a GitHub Actions workflow (`.github/workflows/build.yml`) that automatically builds executables for all platforms. Push a version tag (e.g., `git tag v1.0.0 && git push --tags`) to trigger a build and create a GitHub Release.

---

## Troubleshooting

| Problem                       | Solution                                                                               |
| ----------------------------- | -------------------------------------------------------------------------------------- |
| macOS blocks the app          | Right-click → "Open" → click "Open" in the dialog                                      |
| macOS app crashes immediately | Download the `.zip` file from Releases and extract it. Do not download the raw binary. |
| Linux: "Permission denied"    | Run `chmod +x FakeNewsAnnotator-Linux` first                                           |
| Windows SmartScreen warning   | Click "More info" → "Run anyway"                                                       |
| Drag and drop not working     | Use the **Browse** or **Paste** buttons instead                                        |
| App window is too small       | Drag the window edges to resize it                                                     |
