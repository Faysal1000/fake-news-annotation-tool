# 📰 Fake News Dataset Annotator

A standalone GUI tool for collecting a multimodal fake news detection dataset. Multiple annotators can use this tool to enter news text, attach images, classify entries as Fake or Real, and specify the type of fake news. All data is saved in a structured CSV file with images stored locally.

**No coding knowledge required** — download a single file, double-click, and start annotating.

---

## ⬇️ Download & Run

Go to the [**Releases**](../../releases/latest) page and download the file for your operating system:

| File | Platform |
|------|----------|
| `FakeNewsAnnotator-Windows.exe` | Windows 10/11 (64-bit) |
| `FakeNewsAnnotator-macOS-AppleSilicon.zip` | macOS (Apple M1/M2/M3/M4) |
| `FakeNewsAnnotator-macOS-Intel.zip` | macOS (Intel processors) |
| `FakeNewsAnnotator-Linux` | Ubuntu / Debian / Fedora |

### How to run

1. **Download** the file for your OS from the [Releases](../../releases/latest) page
2. **Place it in a folder** (e.g., a new folder on your Desktop)
3. **If downloading a `.zip` (macOS)**: Double-click to extract it first. You will get a `FakeNewsAnnotator.app` file.
4. **Double-click** the executable (or `.app`) to launch the tool

> **macOS users:** If macOS blocks the app, right-click → "Open" → click "Open" in the dialog. You only need to do this once.

> **Linux users:** You may need to make the file executable first: `chmod +x FakeNewsAnnotator-Linux`, then double-click or run `./FakeNewsAnnotator-Linux`.

The tool will automatically create `dataset.csv`, `images/` folder, and a config file **in the same folder** where the executable is located.

---

## 🖥️ How to Use

1. **Enter your name** in the "Annotator Name" field (saved automatically for next time)
2. **Select a label**: click either **Fake** or **Real** (required)
3. **If Fake**: select the **Fake News Type** — Misinformation, Rumor, or Clickbait (required for Fake entries)
4. **Select News Category** from the dropdown — Politics, Health, Science, etc. (required)
5. **Select Source Category** from the dropdown — News Channel, Facebook, Twitter, etc. (required)
6. **Enter Source Link** — paste the URL where the news was found (optional)
7. **Enter Heading** — the headline or title of the news (optional)
8. **Enter the news text** in the text area (required if no image)
9. **Add images** using one of three methods (required if no text):
   - Click **"Browse Images"** to select files
   - Click **"Paste from Clipboard"** to paste a screenshot
   - Drag and drop images into the drop zone
10. Click **"💾 Save Entry"**
11. A confirmation popup will appear. Fields are cleared for the next entry.

### Validation Rules

- **Annotator name** is required
- **Label** (Fake/Real) is required
- **Fake News Type** is required when label is Fake
- **News Category** is required
- **Source Category** is required
- At least **text or image** must be provided
- If text is fewer than 10 words, a warning will appear (you can still save)
- Multiple images can be attached to a single entry

---

## 📁 Output Files

After saving entries, the following files are created **next to the executable**:

```
YourFolder/
├── FakeNewsAnnotator.exe    # The tool (or .app / Linux binary)
├── dataset.csv              # Your annotations (auto-created)
├── .annotator_config.json   # Remembers your name (auto-created)
└── images/                  # Saved images (auto-created)
    ├── Fake_00001_uuid_YourName.jpg
    ├── Real_00002_uuid_YourName.png
    └── ...
```

### CSV Columns

| Column | Description |
|--------|-------------|
| `id` | Unique identifier (UUID) — safe for merging across annotators |
| `heading` | Optional headline / title of the news item |
| `text` | News content body |
| `image_path` | Relative path(s) to image(s), separated by `;` if multiple |
| `label` | `Fake` or `Real` |
| `multi_category` | Fake news sub-type (`Misinformation`, `Rumor`, `Clickbait`) or `Real` |
| `source` | Source link / URL (optional) |
| `source_category` | Platform where news was found (e.g., `Facebook`, `News Channel`) |
| `category` | News topic category (e.g., `Politics`, `Health`) |
| `annotator` | Name of the person who annotated this entry |
| `timestamp` | ISO-format datetime when the entry was saved |

### Image Naming Convention

Images are saved with this naming pattern:

```
{Label}_{count}_{uuid}_{annotator}.{extension}
```

Example: `Fake_00042_550e8400-e29b-41d4-a716-446655440000_Faysal.jpg`

---

## 📤 Submitting Your Data

When you are done annotating, send these to the project lead:

1. Your `dataset.csv` file
2. Your entire `images/` folder

Keep the folder structure intact so the image paths in the CSV remain valid.

---

## 🛠️ For Developers

### Running from source

```bash
# Clone the repository
git clone https://github.com/Faysal1000/fake-news-annotation-tool.git
cd fake-news-annotation-tool

# Install dependencies
pip install -r requirements.txt

# Run the tool
python annotator_tool.py
```

### Building locally

```bash
pip install pyinstaller
python build.py
```

The executable will be created in the `dist/` folder.

### GitHub Actions CI/CD

The project includes a GitHub Actions workflow (`.github/workflows/build.yml`) that automatically builds executables for all platforms:

- **Automatic**: Push a version tag (e.g., `git tag v1.0.0 && git push --tags`) to trigger a build and create a GitHub Release with all executables
- **Manual**: Go to Actions tab → "Build Annotator Executables" → "Run workflow"

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| macOS blocks the app | Right-click → "Open" → click "Open" in the dialog |
| macOS app crashes immediately | Download the `.zip` file from Releases and extract it. Do not download the raw binary. |
| Linux: "Permission denied" | Run `chmod +x FakeNewsAnnotator-Linux` first |
| Windows SmartScreen warning | Click "More info" → "Run anyway" |
| Drag and drop not working | Use the **Browse** or **Paste** buttons instead |
| App window is too small | Drag the window edges to resize it |

---

## 📋 Categories Reference

### News Categories
Politics, Health, Science, Technology, Sports, Entertainment, Business, Education, Environment, International, Miscellaneous

### Source Categories
News Channel, Newspaper, Facebook, Twitter, Instagram, Reddit, YouTube, Blog, Website, Miscellaneous

### Fake News Types (Multi-Category)
- **Misinformation** — False information spread without intent to deceive
- **Rumor** — Unverified claims spread through informal channels
- **Clickbait** — Misleading headlines designed to attract clicks
