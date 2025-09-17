import markdown


def render_docs(file_path):
    """
    Render markdown documentation with LaTeX math support using MathJax.

    Returns embeddable HTML content optimized for Django templates.
    """
    with open(file_path, 'r') as file:
        markdown_content = file.read()
    md = markdown.Markdown(extensions=[
        'codehilite',
        'fenced_code',
        'tables',
        'toc'
    ])
    html_content = md.convert(markdown_content)
    # Return content with inline MathJax for template embedding
    return f"""
        <!-- MathJax Configuration (inline) -->
        <script>
            if (!window.MathJax) {{
                window.MathJax = {{
                    tex: {{
                        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                        processEscapes: true,
                        processEnvironments: true
                    }},
                    options: {{
                        skipHtmlTags: [
                            'script', 'noscript', 'style',
                            'textarea', 'pre', 'code'
                        ]
                    }}
                }};

                // Load MathJax if not already loaded
                if (!document.getElementById('MathJax-script')) {{
                    const script = document.createElement('script');
                    script.id = 'MathJax-script';
                    script.async = true;
                    script.src = 'https://cdn.jsdelivr.net/npm/mathjax@3/' +
                                 'es5/tex-mml-chtml.js';
                    document.head.appendChild(script);
                }}
            }}

            // Reprocess math if MathJax is already loaded
            if (window.MathJax && window.MathJax.typesetPromise) {{
                window.MathJax.typesetPromise();
            }}
        </script>

        <!-- Documentation Content -->
        <div class="docs-content">
            {html_content}
        </div>

        <style>
            .docs-content {{
                line-height: 1.6;
                color: #333;
            }}

            .docs-content h1, .docs-content h2, .docs-content h3,
            .docs-content h4, .docs-content h5, .docs-content h6 {{
                color: #2c3e50;
                margin-top: 25px;
                margin-bottom: 12px;
            }}

            .docs-content h1 {{
                border-bottom: 2px solid #3498db;
                padding-bottom: 8px;
                font-size: 1.5rem;
            }}

            .docs-content h2 {{
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 4px;
                font-size: 1.3rem;
            }}

            .docs-content h3 {{
                font-size: 1.1rem;
            }}

            .docs-content code {{
                background-color: #f8f9fa;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Consolas', monospace;
                font-size: 0.85em;
            }}

            .docs-content pre {{
                background-color: #f8f9fa;
                padding: 12px;
                border-radius: 5px;
                overflow-x: auto;
                border-left: 4px solid #3498db;
                margin: 15px 0;
            }}

            .docs-content pre code {{
                background-color: transparent;
                padding: 0;
            }}

            .docs-content ul, .docs-content ol {{
                padding-left: 20px;
                margin: 10px 0;
            }}

            .docs-content li {{
                margin-bottom: 4px;
            }}

            .docs-content table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
                font-size: 0.9rem;
            }}

            .docs-content th, .docs-content td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}

            .docs-content th {{
                background-color: #f2f2f2;
                font-weight: bold;
            }}

            .docs-content blockquote {{
                border-left: 4px solid #3498db;
                margin: 15px 0;
                padding: 8px 15px;
                background-color: #f8f9fa;
            }}

            /* Math display styling */
            .docs-content .MathJax_Display {{
                margin: 15px 0;
            }}
        </style>
        """.strip()
