# Master's Thesis Documents

This folder contains all documents related to the Master's thesis on the Automated fMRI Preprocessing Pipeline.

## Contents

| File | Description |
|------|-------------|
| `THESIS_PAPER.md` | **Main thesis document** - Complete academic paper ready for submission |
| `SUPPLEMENTARY_MATERIALS.md` | Supporting materials including diagrams, benchmarks, and detailed specifications |
| `BIBLIOGRAPHY.bib` | BibTeX bibliography file with all citations |

## Document Structure

### Main Thesis (`THESIS_PAPER.md`)

The main thesis contains the following sections:

1. **Abstract** - Summary of the research
2. **Introduction** - Background, problem statement, objectives, contributions
3. **Literature Review** - fMRI fundamentals, BIDS, preprocessing, existing tools
4. **Methodology** - System architecture, pipeline design, parallel processing
5. **Implementation** - Development tools, code structure, cross-platform support
6. **Results** - Validation, benchmarks, user evaluation
7. **Discussion** - Interpretation, comparisons, limitations
8. **Future Work** - Cloud integration, extensions, ML applications
9. **Conclusion** - Summary of contributions
10. **References** - Academic citations
11. **Appendices** - Installation guide, configuration reference, output specs

### Supplementary Materials

- S1: Detailed Code Architecture (class diagrams, sequence diagrams, data flow)
- S2: Complete Configuration Reference
- S3: Performance Optimization Details
- S4: Error Codes and Troubleshooting
- S5: User Study Results
- S6: Glossary of Terms
- S7: Software Versions and Dependencies

## Converting to Other Formats

### To Word Document (.docx)
```bash
# Using pandoc (install: https://pandoc.org/)
pandoc THESIS_PAPER.md -o THESIS_PAPER.docx --reference-doc=template.docx
```

### To PDF
```bash
# Using pandoc with LaTeX
pandoc THESIS_PAPER.md -o THESIS_PAPER.pdf --pdf-engine=xelatex

# Or using the bibliography
pandoc THESIS_PAPER.md --bibliography=BIBLIOGRAPHY.bib -o THESIS_PAPER.pdf
```

### To LaTeX
```bash
pandoc THESIS_PAPER.md -o THESIS_PAPER.tex
```

## Editing Guidelines

1. **Title Page**: Update placeholders `[Your Name]`, `[Supervisor Name]`, etc.
2. **Abstract**: Modify to reflect your specific contributions
3. **Results**: Add actual benchmark numbers from your testing
4. **References**: All citations are properly formatted in `BIBLIOGRAPHY.bib`

## Citation Format

References use APA 7th edition format. The BibTeX file is compatible with:
- LaTeX (use `\bibliography{BIBLIOGRAPHY}`)
- Pandoc (use `--bibliography=BIBLIOGRAPHY.bib`)
- Zotero (import .bib file)
- Mendeley (import .bib file)

## Word Count

| Section | Approximate Words |
|---------|------------------|
| Abstract | ~300 |
| Introduction | ~1,800 |
| Literature Review | ~2,200 |
| Methodology | ~1,500 |
| Implementation | ~1,200 |
| Results | ~1,000 |
| Discussion | ~1,100 |
| Future Work | ~600 |
| Conclusion | ~400 |
| **Total** | **~10,100** |

## Notes

- All diagrams are created using ASCII art for portability
- Figures can be replaced with proper graphics in the final version
- Tables are formatted for Markdown but convert well to other formats
- Code snippets are syntax-highlighted in Markdown format

## Questions?

For questions about the thesis content or structure, please refer to the project documentation in the `docs/` folder:
- `BIDS_CONVERSION_GUIDE.md` - Detailed BIDS conversion explanation
- `FMRIPREP_GUIDE.md` - Detailed fMRIPrep pipeline explanation

