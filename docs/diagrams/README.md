# Diagram sources

The SVG architecture diagrams in this directory are generated from the adjacent Mermaid source
files. Edit the `.mmd` file first, then regenerate the image so the source and rendered artifact stay
in sync.

```bash
npx -y @mermaid-js/mermaid-cli@12.2.0 -i docs/diagrams/system-architecture.mmd -o docs/diagrams/system-architecture.svg -c docs/diagrams/mermaid-config.json -b transparent
npx -y @mermaid-js/mermaid-cli@12.2.0 -i docs/diagrams/review-sequence.mmd -o docs/diagrams/review-sequence.svg -c docs/diagrams/mermaid-config.json -b transparent
npx -y @mermaid-js/mermaid-cli@12.2.0 -i docs/diagrams/audit-pipeline.mmd -o docs/diagrams/audit-pipeline.svg -c docs/diagrams/mermaid-config.json -b transparent
```

The generated SVG files are committed so GitHub, documentation sites, and offline readers can show
the diagrams without requiring Mermaid at runtime.
