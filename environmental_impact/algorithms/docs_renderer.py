import markdown


def render_docs(file_path):
    with open(file_path, 'r') as file:
        markdown_content = file.read()
    html_content = markdown.markdown(markdown_content)
    return html_content
