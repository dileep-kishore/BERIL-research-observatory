#!/usr/bin/env python3
"""
Execute the BERDL pangenome exploration notebook and handle errors gracefully.
"""

import sys
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError

def execute_notebook(input_path, output_path):
    """Execute a Jupyter notebook and save the result."""

    print(f"Loading notebook: {input_path}")
    with open(input_path, 'r') as f:
        nb = nbformat.read(f, as_version=4)

    # Configure execution
    ep = ExecutePreprocessor(
        timeout=3600,  # 60 minutes per cell (for large distance computations)
        kernel_name='python3',
        allow_errors=True  # Continue execution even if cells error
    )

    print("Executing notebook...")
    print("=" * 60)

    try:
        ep.preprocess(nb, {'metadata': {'path': './'}})
        print("\n" + "=" * 60)
        print("✅ Notebook execution completed")
    except Exception as e:
        print(f"\n⚠️  Execution completed with errors: {e}")

    # Save the executed notebook
    print(f"Saving results to: {output_path}")
    with open(output_path, 'w') as f:
        nbformat.write(nb, f)

    # Print summary of cell execution
    print("\n" + "=" * 60)
    print("Execution Summary:")
    print("=" * 60)

    error_cells = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type == 'code':
            outputs = cell.get('outputs', [])
            has_error = any(output.get('output_type') == 'error' for output in outputs)
            if has_error:
                error_cells.append(i)
                print(f"Cell {i}: ❌ ERROR")
            else:
                print(f"Cell {i}: ✅ OK")

    if error_cells:
        print(f"\n⚠️  {len(error_cells)} cell(s) had errors, but execution continued")
        print(f"Error cells: {error_cells}")
    else:
        print("\n✅ All cells executed successfully!")

    return len(error_cells) == 0

if __name__ == "__main__":
    # Accept command line arguments or use defaults
    if len(sys.argv) >= 3:
        input_notebook = sys.argv[1]
        output_notebook = sys.argv[2]
    elif len(sys.argv) == 2:
        input_notebook = sys.argv[1]
        output_notebook = input_notebook.replace('.ipynb', '_executed.ipynb')
    else:
        input_notebook = "berdl_pangenome_exploration.ipynb"
        output_notebook = "berdl_pangenome_exploration_executed.ipynb"

    success = execute_notebook(input_notebook, output_notebook)

    print("\n" + "=" * 60)
    print(f"Results saved to: {output_notebook}")
    print("You can now open this file in VSCode to see all outputs!")
    print("=" * 60)

    sys.exit(0 if success else 1)
