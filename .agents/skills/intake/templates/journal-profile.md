# Journal profile: <Journal name>

_Researched <YYYY-MM-DD> by the intake skill. Sources: <guidelines URL>, <template URL>, OpenAlex, ..._

## Identity
- Publisher / ISSN (print, online) / ISSN-L:
- Open access model, APC (USD), indexing (Scopus / WoS / DOAJ):
- Homepage / guide for authors:

## Aims & scope (paraphrased)
- ...
- What kinds of theory / simulation papers appear (from recent issues):

## Article type: <type>
- Requirements specific to this type (length, structure, review process):

## LaTeX template & references
- Template / class: <e.g. elsarticle, preprint option> — downloaded to `templates/<name>/` (or: none; generic)
- Reference style: <numbered/author-year>, bst/biblatex style: <...>
- Special macros / front matter (highlights, keywords env, MSC codes, ...):

## Limits
| item | limit | source |
|---|---|---|
| words (what is counted) | | |
| abstract words | | |
| pages | | |
| figures / tables | | |
| references | | |
| keywords | | |

## Required sections and files
- Sections:
- Separate files (highlights, graphical abstract, cover letter, ...):
- Statements (data availability, code availability, CRediT, competing interests, funding, ethics):

## AI-use disclosure policy (for the author; the agent writes no AI statement)
- Requirement (≤ 1 sentence quote with URL):
- Where the statement goes / required wording:
- What is allowed / forbidden (e.g. AI as author, AI-generated images):

## Constraint check (from project.json)
- open access: ... | indexing: ... | deadline: ... | max APC: ... → conflicts: none / <list>

## Machine-readable (used by `./ra limits`)
```json
{
  "limits": {
    "words_max": null,
    "abstract_words_max": null,
    "pages_max": null,
    "figures_max": null,
    "tables_max": null,
    "references_max": null,
    "keywords_min": null,
    "keywords_max": null,
    "title_chars_max": null
  },
  "words_counting": "e.g. main text excluding abstract, references, captions",
  "documentclass": null,
  "reference_style": null,
  "required_sections": ["Introduction", "Conclusion"],
  "required_files": [],
  "ai_disclosure": {"required": true, "placement": "", "wording_hint": ""}
}
```

## Unknowns
- <item>: UNKNOWN (checked: <where>)
