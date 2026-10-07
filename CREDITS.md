# Credits

## Development assistance

Kosh was built with assistance from **OpenAI Codex** and **Anthropic Claude**:

- **OpenAI Codex** assisted with implementation, integration, testing, packaging, documentation and review.
- **Anthropic Claude**, including **Claude Opus**, assisted with product design and independent feature, presentation and privacy reviews.

These credits recognise AI-assisted development. They do not imply endorsement, sponsorship or human authorship by OpenAI or Anthropic. Project decisions and responsibility remain with the maintainer.

## Inspiration and components

Kosh is an original Windows research desk. The original research-workspace inspiration is **Beeblio by Al Harkan ([alharkan7](https://github.com/alharkan7))**: [Beeblio source repository](https://github.com/alharkan7/beeblio-oss). Its public source was inspected to understand workflow and licence. No Beeblio application code, branding or visual assets were copied into Kosh. This credit does not imply endorsement, affiliation or authorship of Kosh by the Beeblio creator. Beeblio retains its own terms/notices.

Other approved workflow references were [Jenni](https://jenni.ai/), [Paperpal](https://paperpal.com/), [SciSpace](https://scispace.com/), [Yomu](https://www.yomu.ai/), [Elicit](https://elicit.com/) and [Zotero](https://www.zotero.org/). Design observations included Lekh and public [Mobbin](https://mobbin.com/) screens. These are inspiration credits, not copied code/assets, bundled services or claims of equal product quality. The original Kosh icon is included with the application source.

The document runtime uses Python/SQLite, PyMuPDF/MuPDF, python-docx, lxml and typing_extensions. Microsoft Edge and .NET Framework are separately installed Windows prerequisites. The prepared OCR language material comes from the Tesseract project's [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) English and [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) Hindi/Punjabi repositories; their captured Apache-2.0 notices and hashes must accompany any release bundling those data.

Offline citation formatting uses **[citeproc-js](https://github.com/Juris-M/citeproc-js) by Frank Bennett**, under its offered AGPL v3-or-later option, and the **[Citation Style Language project](https://citationstyles.org/)** styles/locales under CC-BY-SA-3.0. Kosh retains the upstream author/contributor lists inside the style XML and translator lists inside the locale XML. APA 7 and IEEE use pinned upstream styles; the Vancouver option uses the official NLM citation-sequence independent parent. The pinned commit IDs, source URLs and captured hashes are in [vendor/csl/components.json](vendor/csl/components.json), with upstream licence/README material beside the files. Citeproc-js is included dependency code; the earlier research-product inspiration credits do not describe this dependency as original Kosh code.

The prepared installer includes **[Node.js](https://nodejs.org/)** 24.14.1 as `tools/node/node.exe` to run that processor locally. Its included LICENSE contains Node and incorporated-component notices; the matching source archive accompanies the prepared legal bundle. Citation processing downloads no runtime, style, locale or document, and does not use AI.

Optional local semantic retrieval can use [nomic-embed-text through Ollama](https://ollama.com/library/nomic-embed-text). Its prepared component receipt captures the selected model/layers and Apache-2.0 notice. Local model installation is separate from the Kosh installer; no model weights/accounts are silently bundled or downloaded by the app. Codex, Claude and Ollama remain separate installed products with their own terms and usage conditions.

Public catalogue metadata/available abstracts come from explicitly queried PubMed (NLM/NCBI), Crossref, Europe PMC or OpenAlex. Results retain provider provenance; index records are not full papers or independently verified academic facts. Combined queries preserve provider attribution and disclose failures.

Local PDF compilation uses **[Tectonic](https://tectonic-typesetting.github.io/)** and a selected TeX Live/LaTeX resource bundle. Credit belongs to the Tectonic contributors, LaTeX Project, American Mathematical Society, package maintainers, TeX Gyre font designers and locale/data contributors identified in their retained source and documentation archives. Compiler and package sources, licences and hash receipts accompany the installer. Kosh adds Chicago note and 63 official CSL locales while preserving their upstream attribution.

The mathematics font resources also credit **Donald E. Knuth** for Computer Modern, the **American Mathematical Society** for AMSFonts, and **Bogusław Jackowski and Janusz M. Nowacki** for Latin Modern. Original font notices, reserved names, corresponding archive material and SIL Open Font License/GUST Font License material are retained. Kosh does not claim authorship of these fonts or supply every upstream font-construction tool.

See [THIRD_PARTY.md](THIRD_PARTY.md) and the actual release's inventory/source/hash receipts for dependency notices and supplied material. Prepared source or licence text is not a certificate of arbitrary future redistribution or a clean-machine installation test.
