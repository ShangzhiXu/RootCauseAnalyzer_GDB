import json
import os
import html

# Define file paths
JSON_FILE = 'output.json'
SOURCE_CODE_FILE = 'source.c'
OUTPUT_HTML_FILE = 'interactive_code.html'


def load_json_data(file_path):
    """
    Load JSON data from the specified file path.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        dict: Parsed JSON data.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"JSON file not found at path: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:  # Specify UTF-8 encoding
        data = json.load(f)
    return data


def load_source_code(file_path):
    """
    Load source code from the specified file path.

    Args:
        file_path (str): Path to the source code file.

    Returns:
        list: List of source code lines.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source code file not found at path: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:  # Specify UTF-8 encoding
        lines = f.readlines()
    return lines


def generate_html(breakpoints, source_code):
    """
    Generate HTML content with source code and interactive buttons in a two-column layout.

    Args:
        breakpoints (list): List of breakpoint dictionaries.
        source_code (list): List of source code lines.

    Returns:
        str: Generated HTML content.
    """
    # Map line numbers to breakpoint data
    breakpoint_map = {}
    for bp in breakpoints:
        line = bp.get('line')
        if line:
            if line not in breakpoint_map:
                breakpoint_map[line] = []
            breakpoint_map[line].append(bp)

    # Start building HTML content
    html_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Interactive Code Visualization</title>
        <!-- Highlight.js CSS -->
        <link rel="stylesheet"
              href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/default.min.css">
        <!-- Font Awesome for Icons -->
        <link rel="stylesheet"
              href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f0f2f5;
                margin: 0;
                padding: 20px;
                color: #333;
            }
            h1 {
                text-align: center;
                color: #2c3e50;
                margin-bottom: 20px;
            }
            .container {
                display: flex;
                flex-direction: row;
                gap: 20px;
                max-width: 1200px;
                margin: auto;
                flex-wrap: wrap;
            }
            .code-container {
                flex: 2;
                min-width: 300px;
            }
            .state-container {
                flex: 1;
                min-width: 250px;
            }
            .code-container h2,
            .state-container h2 {
                margin-bottom: 10px;
                color: #2c3e50;
            }
            #code-container {
                background-color: #ffffff;
                padding: 10px;
                border-radius: 8px;
                width: 100%;
                overflow: auto;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                transition: background-color 0.3s ease;
                line-height: 1.5;
                font-family: 'Courier New', Courier, monospace;
            }
            .code-line {
                display: flex;
                align-items: center;
                margin: 0;
                padding: 2px 0;
            }
            .line-number {
                width: 40px;
                text-align: right;
                padding-right: 5px;
                user-select: none;
                color: #555;
                font-weight: bold;
                font-size: 14px;
            }
            .code-text {
                flex-grow: 1;
                white-space: pre-wrap;
                word-wrap: break-word;
                color: #2c3e50;
                font-size: 14px;
                line-height: 1.5;
            }
            .breakpoint-button {
                margin-left: 5px;
                padding: 2px 6px;
                font-size: 12px;
                cursor: pointer;
                border: none;
                border-radius: 4px;
                background-color: #e74c3c;
                color: white;
                transition: background-color 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .breakpoint-button i {
                margin-right: 3px;
            }
            .breakpoint-button:hover {
                background-color: #c0392b;
            }
            #state-display {
                padding: 15px;
                border-radius: 8px;
                background-color: #ffffff;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                height: 100%;
                overflow-y: auto;
            }
            #state-display h2 {
                margin-top: 0;
                color: #2c3e50;
                font-size: 20px;
                border-bottom: 2px solid #3498db;
                padding-bottom: 5px;
                margin-bottom: 15px;
            }
            .state-section {
                margin-bottom: 10px;
                padding: 8px;
                border-left: 4px solid #3498db;
                background-color: #ecf0f1;
                border-radius: 4px;
            }
            .state-section b {
                display: block;
                margin-bottom: 4px;
                color: #2980b9;
            }
            /* Highlight active line */
            .active-line {
                background-color: rgba(52, 152, 219, 0.2);
                border-radius: 4px;
            }
            /* Style for folded values */
            .folded-value {
                display: inline;
            }
            .folded-value a {
                color: #3498db;
                text-decoration: none;
                margin-left: 5px;
                font-size: 12px;
            }
            .folded-value a:hover {
                text-decoration: underline;
            }
            /* Collapsible nested objects and arrays */
            .collapsible {
                cursor: pointer;
                color: #2980b9;
                text-decoration: underline;
                margin-left: 5px;
                font-size: 12px;
            }
            .nested {
                display: none;
                margin-left: 20px;
                border-left: 2px solid #bdc3c7;
                padding-left: 10px;
            }
            .active {
                display: block;
            }
            /* Expand/Collapse All Buttons */
            .expand-collapse-buttons {
                margin-bottom: 10px;
            }
            .expand-collapse-buttons button {
                margin-right: 5px;
                padding: 5px 10px;
                font-size: 12px;
                cursor: pointer;
                border: none;
                border-radius: 4px;
                background-color: #3498db;
                color: white;
                transition: background-color 0.3s ease;
            }
            .expand-collapse-buttons button:hover {
                background-color: #2980b9;
            }
            /* Responsive Design */
            @media (max-width: 768px) {
                .container {
                    flex-direction: column;
                }
                .line-number {
                    width: 30px;
                    font-size: 12px;
                }
                .breakpoint-button {
                    padding: 2px 4px;
                    font-size: 11px;
                }
                #state-display {
                    padding: 10px;
                }
                .code-text {
                    font-size: 13px;
                }
                #state-display h2 {
                    font-size: 18px;
                }
                .state-section {
                    padding: 6px;
                }
                .state-section b {
                    margin-bottom: 2px;
                }
            }
        </style>
    </head>
    <body>
        <h1>Interactive Code Visualization</h1>
        <div class="container">
            <div class="code-container">
                <h2>Source Code</h2>
                <div class="expand-collapse-buttons">
                    <button onclick="expandAll()">Expand All</button>
                    <button onclick="collapseAll()">Collapse All</button>
                </div>
                <div id="code-container">
    '''

    # Generate code lines with line numbers and buttons
    for idx, line in enumerate(source_code, start=1):
        stripped_line = line.rstrip('\n').replace('<', '&lt;').replace('>', '&gt;')
        html_content += f'<div class="code-line">'
        # Line number
        html_content += f'<span class="line-number">{idx}</span>'
        # Code text with syntax highlighting
        html_content += f'<span class="code-text"><code class="language-c">{stripped_line}</code></span>'
        # If there's a breakpoint on this line, add a button
        if idx in breakpoint_map:
            html_content += f' <button class="breakpoint-button" onclick="showState({idx})"><i class="fa fa-eye"></i> Show State</button>'
        html_content += '</div>\n'

    # Close the code container div and add the state display section
    html_content += '''
                </div>
            </div>
            <div class="state-container">
                <h2>State Display</h2>
                <div id="state-display">
                    <h2>State at Line <span id="state-line">N/A</span></h2>
                    <div id="state-content">
                        <p>Click on the "Show State" button next to a line to view its state.</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Highlight.js Library -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
        <script>hljs.highlightAll();</script>

        <!-- Font Awesome for Icons -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/js/all.min.js"></script>

        <script>
            // Breakpoint data from JSON
            const breakpoints = 
    '''

    # Embed the breakpoint_map into JavaScript
    # Convert breakpoint_map to JSON and embed
    breakpoint_json = json.dumps(breakpoint_map, indent=4)
    html_content += breakpoint_json + ';\n'

    # Add JavaScript functions
    html_content += '''
            // Function to display state
            function showState(lineNumber) {
                const stateDisplay = document.getElementById('state-display');
                const stateLine = document.getElementById('state-line');
                const stateContent = document.getElementById('state-content');

                // Clear previous highlight
                const active = document.querySelector('.active-line');
                if (active) {
                    active.classList.remove('active-line');
                }

                // Highlight the current line
                const codeContainer = document.getElementById('code-container');
                const lines = codeContainer.getElementsByClassName('code-line');
                if (lines[lineNumber - 1]) {
                    lines[lineNumber - 1].classList.add('active-line');
                }

                // Get breakpoint data for the line
                const bps = breakpoints[lineNumber];
                if (!bps) {
                    stateContent.innerHTML = '<p>No state information available for this line.</p>';
                    stateLine.textContent = lineNumber;
                    return;
                }

                // Build HTML content for the state
                let html = '';
                bps.forEach((bp, index) => {
                    html += `<div class="state-section"><b>Breakpoint ${index + 1}:</b>`;
                    if (bp.location) {
                        html += `<strong>Location:</strong> ${bp.location}<br>`;
                    }
                    if (bp.state) {
                        html += `<strong>State:</strong> ${bp.state}<br>`;
                    }

                    // Recursive function to escape HTML special characters
                    function escapeHTML(str) {
                        if (typeof str !== 'string') {
                            str = JSON.stringify(str);
                        }
                        return str.replace(/&/g, '&amp;')
                                  .replace(/</g, '&lt;')
                                  .replace(/>/g, '&gt;')
                                  .replace(/"/g, '&quot;')
                                  .replace(/'/g, '&#039;');
                    }

function toggleNested(varID) {
    const nestedDiv = document.getElementById(varID + '_nested');
    if (nestedDiv) {
        nestedDiv.classList.toggle('active');
        if (!nestedDiv.classList.contains('active')) {
            // Collapse all nested children as well
            const allNested = nestedDiv.querySelectorAll('.nested');
            allNested.forEach(child => {
                child.classList.remove('active');
            });
        }
    }
}


                    // Recursive function to create variable HTML

function createVariableHTML(key, value, varID) {
    let escapedKey = escapeHTML(key);
    if (Array.isArray(value)) {
        // Begin array handling
        let html = `${escapedKey} = [<br><div class="nested" id="${varID}_nested">`;
        html += value.map((item, idx) => {
            const arrayItemID = `${varID}_${idx}`;
            if (typeof item === 'object' && item !== null) {
                // Object handling for nested arrays
                return `<span id="${arrayItemID}_container">${idx} = {<span class="collapsible" onclick="toggleNested('${arrayItemID}')">[+/-]</span><div id="${arrayItemID}_nested" class="nested">` + createVariableHTML(`${idx}`, item, arrayItemID) + `}</div>}</span>`;
            } else {
                // Primitive type handling within arrays
                let itemValue = escapeHTML(JSON.stringify(item));
                return `<span class="array-item">${idx} = ${itemValue}</span>`;
            }
        }).join('<br>');  // Use <br> to separate array elements
        html += `</div>]<br>`;
        return html;
    } else if (typeof value === 'object' && value !== null) {
        // Handle nested objects
        let html = `${escapedKey} = { <span class="collapsible" onclick="toggleNested('${varID}')">[+/-]</span><div id="${varID}_nested" class="nested">`;
        for (const [subKey, subValue] of Object.entries(value)) {
            const fieldID = `${varID}_${subKey}`;
            html += createVariableHTML(subKey, subValue, fieldID);
        }
        html += `}</div><br>`;
        return html;
    } else {
        // Handle primitive types
        let escapedValue = escapeHTML(value);
        return `${escapedKey} = ${escapedValue}<br>`;
    }
}



                    // Add variable sections
                    if (bp.arguments && Object.keys(bp.arguments).length > 0) {
                        html += `<strong>Arguments:</strong><br>`;
                        for (const [key, value] of Object.entries(bp.arguments)) {
                            const varID = `arg_${lineNumber}_${index}_${key}`;
                            html += createVariableHTML(key, value, varID);
                        }
                    }
                    if (bp.local_vars && Object.keys(bp.local_vars).length > 0) {
                        html += `<strong>Local Variables:</strong><br>`;
                        for (const [key, value] of Object.entries(bp.local_vars)) {
                            const varID = `local_${lineNumber}_${index}_${key}`;
                            html += createVariableHTML(key, value, varID);
                        }
                    }
                    if (bp.global_vars && Object.keys(bp.global_vars).length > 0) {
                        html += `<strong>Global Variables:</strong><br>`;
                        for (const [key, value] of Object.entries(bp.global_vars)) {
                            const varID = `global_${lineNumber}_${index}_${key}`;
                            html += createVariableHTML(key, value, varID);
                        }
                    }
                    html += '</div>';
                });

                // Update the display
                stateLine.textContent = lineNumber;
                stateContent.innerHTML = html;
            }

            // Function to expand folded values
            function expandValue(varID) {
                const element = document.getElementById(varID);
                const fullValue = element.getAttribute('data-full-value');
                element.innerHTML = `${fullValue} <a href="#" onclick="collapseValue('${varID}'); return false;">Show Less</a>`;
            }

            // Function to collapse expanded values
            function collapseValue(varID) {
                const element = document.getElementById(varID);
                const fullValue = element.getAttribute('data-full-value');
                const MAX_VALUE_LENGTH = 50;
                let truncatedValue = fullValue.substring(0, MAX_VALUE_LENGTH) + '...';
                element.innerHTML = `"${truncatedValue}" <a href="#" onclick="expandValue('${varID}'); return false;">Show More</a>`;
            }

            // Function to toggle nested objects and arrays
            function toggleNested(varID) {
                const nestedDiv = document.getElementById(varID + '_nested');
                if (nestedDiv) {
                    nestedDiv.classList.toggle('active');
                }
            }

            // Optional Enhancement: Handle expanding and collapsing of string arrays
            function expandString(varID, fullString) {
                const element = document.getElementById(varID);
                element.innerHTML = `"${fullString}" <a href="#" onclick="collapseString('${varID}', '${fullString.substring(0, 50)}...'); return false;">Show Less</a>`;
            }

            function collapseString(varID, truncatedStr) {
                const element = document.getElementById(varID);
                const fullValue = element.getAttribute('data-full-value');
                element.innerHTML = `"${truncatedStr}" <a href="#" onclick="expandString('${varID}', '${fullValue}'); return false;">Show More</a>`;
            }

            // Function to expand all nested elements
            function expandAll() {
                const nestedElements = document.querySelectorAll('.nested');
                nestedElements.forEach(elem => {
                    elem.classList.add('active');
                });
            }

            // Function to collapse all nested elements
            function collapseAll() {
                const nestedElements = document.querySelectorAll('.nested');
                nestedElements.forEach(elem => {
                    elem.classList.remove('active');
                });
            }
        </script>
    </body>
    </html>
    '''

    return html_content


def save_html(content, file_path):
    """
    Save the generated HTML content to a file.

    Args:
        content (str): HTML content.
        file_path (str): Path to save the HTML file.
    """
    with open(file_path, 'w', encoding='utf-8') as f:  # Specify UTF-8 encoding
        f.write(content)
    print(
        f"Interactive code visualization has been saved to '{file_path}'. Open this file in a web browser to view it.")


def main():
    try:
        # Load JSON data
        data = load_json_data(JSON_FILE)
        breakpoints = data.get('breakpoints', [])
        if not breakpoints:
            print("No breakpoints found in the JSON data.")
            return

        # Load source code
        source_code = load_source_code(SOURCE_CODE_FILE)
        if not source_code:
            print("Source code file is empty.")
            return

        # Generate HTML content
        html_content = generate_html(breakpoints, source_code)

        # Save HTML to file
        save_html(html_content, OUTPUT_HTML_FILE)

    except FileNotFoundError as e:
        print(e)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
    except UnicodeDecodeError as e:
        print(f"Unicode Decode Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
