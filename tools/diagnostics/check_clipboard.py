import sys
from pathlib import Path

# Repo root is two levels up — works no matter where this is run from
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.typer import _get_clipboard, _set_clipboard, type_text

def test_clipboard():
    print("Testing clipboard functions...")
    
    # Original content
    original = _get_clipboard()
    print(f"Original clipboard: {original}")
    
    # Test set/get
    test_str = "Pishper Test String 123"
    print(f"Setting clipboard to: {test_str}")
    if _set_clipboard(test_str):
        new_val = _get_clipboard()
        print(f"New clipboard value: {new_val}")
        if new_val == test_str:
            print("SUCCESS: Set/Get works correctly.")
        else:
            print(f"FAILURE: Expected '{test_str}', got '{new_val}'")
    else:
        print("FAILURE: _set_clipboard failed.")
    
    # Test type_text (simulated)
    print("Testing type_text (restoring clipboard)...")
    type_text("Typing test...")
    print("Check if type_text crashed. If you see this, it didn't crash.")
    
    # Restore original (type_text does it in a thread, we'll do it manually here to be sure)
    if original is not None:
        _set_clipboard(original)
        print("Restored original clipboard.")

if __name__ == "__main__":
    try:
        test_clipboard()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
