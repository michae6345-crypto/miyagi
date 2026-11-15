| state | step 1 (A / B / C) | step 2 (A / B / C) | step 3 (A / B / C) |
|---|---|---|---|
| empty | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| unsaved | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| wrong_folder | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| typo | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL | FAIL / FAIL / FAIL |
| terminal_closed | FAIL / PASS / PASS | FAIL / FAIL / FAIL | PASS / FAIL / FAIL |
| right | FAIL / PASS / PASS | PASS / FAIL / FAIL | PASS / FAIL / FAIL |

| lesson | step | state | result | behaviour | cards shown |
|---|---|---|---|---|---|
| A | s1 | empty | FAIL | stayed open | Question · Add the add function; Stuck on this step? |
| A | s1 | unsaved | FAIL | stayed open | Type this · Add the add function; Stuck on this step?; Save calculator.py |
| A | s1 | wrong_folder | FAIL | stayed open | Type this · Add the add function; Stuck on this step?; Wrong folder? |
| A | s1 | typo | FAIL | stayed open | SyntaxError in calculator.py; Question · Add the add function; Stuck on this step? |
| A | s1 | terminal_closed | FAIL | stayed open | Start: Add the add function; Type this · Add the add function; Stuck on this step? |
| A | s1 | right | FAIL | did NOT pass with the right code | Start: Add the add function; Type this · Add the add function; Stuck on this step? |
| A | s2 | empty | FAIL | stayed open | Question · Run your first output; Where to work; Stuck on this step? |
| A | s2 | unsaved | FAIL | stayed open | Type this · Run your first output |
| A | s2 | wrong_folder | FAIL | passed on code in another folder | (no card) |
| A | s2 | typo | FAIL | stayed open | SyntaxError in calculator.py; Question · Run your first output; Stuck on this step? |
| A | s2 | terminal_closed | FAIL | passed without running the program | (no card) |
| A | s2 | right | PASS | passed | (no card) |
| A | s3 | empty | FAIL | stayed open | Type this · Add three more operations; Where to work; Stuck on this step? |
| A | s3 | unsaved | FAIL | stayed open | Type this · Add three more operations; Save calculator.py |
| A | s3 | wrong_folder | FAIL | stayed open | Type this · Add three more operations; Stuck on this step?; Wrong folder? |
| A | s3 | typo | FAIL | stayed open | SyntaxError in calculator.py; Question · Add three more operations; Stuck on this step? |
| A | s3 | terminal_closed | PASS | passed (code saved; no terminal needed) | (no card) |
| A | s3 | right | PASS | passed | (no card) |
| B | s1 | empty | FAIL | stayed open | Type this · Create the project file; Where to work; Stuck on this step? |
| B | s1 | unsaved | FAIL | stayed open | Type this · Create the project file; Where to work; Save calculator.py |
| B | s1 | wrong_folder | FAIL | stayed open | Type this · Create the project file; Where to work |
| B | s1 | typo | FAIL | stayed open | NameError in calculator.py; Question · Create the project file; Where to work; Stuck on this step? |
| B | s1 | terminal_closed | PASS | passed (code saved; no terminal needed) | (no card) |
| B | s1 | right | PASS | passed | (no card) |
| B | s2 | empty | FAIL | stayed open | Question · Create the project file; Where to work; Stuck on this step? |
| B | s2 | unsaved | FAIL | stayed open | Type this · Run your first script; Stuck on this step?; Save calculator.py |
| B | s2 | wrong_folder | FAIL | stayed open | Type this · Run your first script; Stuck on this step?; Wrong folder? |
| B | s2 | typo | FAIL | stayed open | NameError in (terminal); Question · Run your first script; Stuck on this step? |
| B | s2 | terminal_closed | FAIL | stayed open (not run yet) | Start: Run your first script; Type this · Run your first script; Stuck on this step? |
| B | s2 | right | FAIL | did NOT pass with the right code | Start: Run your first script; Type this · Run your first script; Stuck on this step? |
| B | s3 | empty | FAIL | stayed open | Question · Add the math functions; Where to work; Stuck on this step? |
| B | s3 | unsaved | FAIL | stayed open | Type this · Add the math functions; Stuck on this step?; Save calculator.py |
| B | s3 | wrong_folder | FAIL | stayed open | Type this · Add the math functions; Stuck on this step?; Wrong folder? |
| B | s3 | typo | FAIL | stayed open | SyntaxError in calculator.py; Question · Add the math functions; Stuck on this step? |
| B | s3 | terminal_closed | FAIL | stayed open | Start: Add the math functions; Type this · Add the math functions; Stuck on this step? |
| B | s3 | right | FAIL | did NOT pass with the right code | Error in calculator.py; Question · Add the math functions; Stuck on this step? |
| C | s1 | empty | FAIL | stayed open | Type this · Print a welcome message; Stuck on this step? |
| C | s1 | unsaved | FAIL | stayed open | Type this · Print a welcome message; Save calculator.py |
| C | s1 | wrong_folder | FAIL | passed on code in another folder | (no card) |
| C | s1 | typo | FAIL | stayed open | NameError in calculator.py; Question · Print a welcome message; Stuck on this step? |
| C | s1 | terminal_closed | PASS | passed (code saved; no terminal needed) | (no card) |
| C | s1 | right | PASS | passed | (no card) |
| C | s2 | empty | FAIL | stayed open | Type this · Run your script; Stuck on this step? |
| C | s2 | unsaved | FAIL | stayed open | Type this · Run your script; Stuck on this step?; Save calculator.py |
| C | s2 | wrong_folder | FAIL | stayed open | Type this · Run your script; Stuck on this step?; Wrong folder? |
| C | s2 | typo | FAIL | stayed open | NameError in (terminal); Question · Run your script; Stuck on this step? |
| C | s2 | terminal_closed | FAIL | stayed open (not run yet) | Start: Run your script; Type this · Run your script; Stuck on this step? |
| C | s2 | right | FAIL | did NOT pass with the right code | Start: Run your script; Type this · Run your script; Stuck on this step? |
| C | s3 | empty | FAIL | stayed open | Question · Write an add function; Stuck on this step? |
| C | s3 | unsaved | FAIL | stayed open | Type this · Write an add function; Stuck on this step?; Save calculator.py |
| C | s3 | wrong_folder | FAIL | stayed open | Type this · Write an add function; Stuck on this step?; Wrong folder? |
| C | s3 | typo | FAIL | stayed open | SyntaxError in calculator.py; Question · Write an add function; Stuck on this step? |
| C | s3 | terminal_closed | FAIL | stayed open | Start: Write an add function; Type this · Write an add function; Stuck on this step? |
| C | s3 | right | FAIL | did NOT pass with the right code | Start: Write an add function; Type this · Write an add function; Stuck on this step? |

### Failing card texts (unique)

| source | title | body | rules broken | seen in |
|---|---|---|---|---|
| card | Stuck on this step? | Skip it, or ask for a hint. | app, file, one | A-s1-empty, A-s1-unsaved, A-s1-wrong_folder, A-s1-typo, A-s1-terminal_closed, A-s1-right (+33) |
| card | Save calculator.py | Save with ⌘S so I can check it. | app | A-s1-unsaved, A-s3-unsaved, B-s1-unsaved, B-s2-unsaved, B-s3-unsaved, C-s1-unsaved (+2) |
| card | Type this · Run your script | Type exactly this in VS Code, then save. | file, one | C-s2-empty, C-s2-unsaved, C-s2-wrong_folder, C-s2-terminal_closed, C-s2-right |
| card | Type this · Add the add function | Type exactly this in calculator.py in VS Code, then save. | one | A-s1-unsaved, A-s1-wrong_folder, A-s1-terminal_closed, A-s1-right |
| card | Type this · Run your first script | Type exactly this in VS Code, then save. | file, one | B-s2-unsaved, B-s2-wrong_folder, B-s2-terminal_closed, B-s2-right |
| card | Type this · Write an add function | Type exactly this in calculator.py in VS Code, then save. | one | C-s3-unsaved, C-s3-wrong_folder, C-s3-terminal_closed, C-s3-right |
| offtrack | SyntaxError in calculator.py | `def` needs a name: line 4 of calculator.py. | app | A-s1-typo, A-s2-typo, B-s3-typo |
| card | Type this · Add three more operations | Type exactly this in calculator.py in VS Code, then save. | one | A-s3-empty, A-s3-unsaved, A-s3-wrong_folder |
| card | Type this · Create the project file | Type exactly this in calculator.py in VS Code, then save. | one | B-s1-empty, B-s1-unsaved, B-s1-wrong_folder |
| card | Type this · Add the math functions | Type exactly this in calculator.py in VS Code, then save. | one | B-s3-unsaved, B-s3-wrong_folder, B-s3-terminal_closed |
| card | Wrong folder? | You're editing calculator.py in Desktop, but this lesson is in python-calculator-e430dc. | app | A-s1-wrong_folder, A-s3-wrong_folder |
| card | Question · Create the project file | NameError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | B-s1-typo, B-s2-empty |
| card | Wrong folder? | You're editing calculator.py in Desktop, but this lesson is in _new. | app | B-s2-wrong_folder, B-s3-wrong_folder |
| card | Question · Add the math functions | SyntaxError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | B-s3-empty, B-s3-typo |
| card | Type this · Print a welcome message | Type exactly this in calculator.py in VS Code, then save. | one | C-s1-empty, C-s1-unsaved |
| card | Wrong folder? | You're editing calculator.py in Desktop, but this lesson is in i-wanna-build-a-calc-in-python-in-vs-cods-9808de. | app | C-s2-wrong_folder, C-s3-wrong_folder |
| card | Question · Add the add function | Which line of calculator.py defines add, and is it there yet? | app | A-s1-empty |
| card | Question · Add the add function | SyntaxError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | A-s1-typo |
| card | Question · Run your first output | What does `python calculator.py` print right now? | app | A-s2-empty |
| card | Type this · Run your first output | Type exactly this in calculator.py in VS Code, then save. | one | A-s2-unsaved |
| card | Question · Run your first output | SyntaxError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | A-s2-typo |
| offtrack | SyntaxError in calculator.py | `def` needs a name: line 7 of calculator.py. | app | A-s3-typo |
| card | Question · Add three more operations | SyntaxError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | A-s3-typo |
| offtrack | NameError in calculator.py | NameError on line 1 of calculator.py: name 'prnt' is not defined. | app | B-s1-typo |
| offtrack | NameError in (terminal) | NameError on line 1 of (terminal): name 'prnt' is not defined. | app, file | B-s2-typo |
| card | Question · Run your first script | NameError in (terminal): what in your code makes that happen, and which value or line would change it? | app, file, words | B-s2-typo |
| offtrack | Error in calculator.py | Error in calculator.py: divide by zero | app | B-s3-right |
| card | Question · Add the math functions | Error in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | B-s3-right |
| offtrack | NameError in calculator.py | NameError in calculator.py: name 'prnt' is not defined. Did you mean: 'print'? | app | C-s1-typo |
| card | Question · Print a welcome message | NameError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | C-s1-typo |
| offtrack | NameError in (terminal) | NameError in (terminal): name 'prnt' is not defined. Did you mean: 'print'? | app, file | C-s2-typo |
| card | Question · Run your script | NameError in (terminal): what in your code makes that happen, and which value or line would change it? | app, file, words | C-s2-typo |
| card | Question · Write an add function | Error in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | C-s3-empty |
| offtrack | SyntaxError in calculator.py | SyntaxError in calculator.py: invalid syntax | app | C-s3-typo |
| card | Question · Write an add function | SyntaxError in calculator.py: what in your code makes that happen, and which value or line would change it? | app, words | C-s3-typo |

### Step action lines and spotlight captions that break a rule

| source | title | body | rules broken | seen in |
|---|---|---|---|---|
| step.started | Create the project file | In calculator.py, type print("Calculator ready") | app | B-s1-empty, B-s1-unsaved, B-s1-wrong_folder, B-s1-typo, B-s1-terminal_closed, B-s1-right (+1) |
| step.started | Add the add function | In calculator.py, type def add(a, b): … | app | A-s1-empty, A-s1-unsaved, A-s1-wrong_folder, A-s1-typo, A-s1-terminal_closed, A-s1-right |
| step.started | Run your first output | In calculator.py, type print(add(2, 3)) | app | A-s2-empty, A-s2-unsaved, A-s2-wrong_folder, A-s2-typo, A-s2-terminal_closed, A-s2-right |
| step.started | Add three more operations | In calculator.py, type def subtract(a, b): … | app | A-s3-empty, A-s3-unsaved, A-s3-wrong_folder, A-s3-typo, A-s3-terminal_closed, A-s3-right |
| step.started | Add the math functions | In calculator.py, type def add(a, b): … | app | B-s3-empty, B-s3-unsaved, B-s3-wrong_folder, B-s3-typo, B-s3-terminal_closed, B-s3-right |
| step.started | Print a welcome message | In calculator.py, type print("Simple Calculator") | app | C-s1-empty, C-s1-unsaved, C-s1-wrong_folder, C-s1-typo, C-s1-terminal_closed, C-s1-right |
| step.started | Run your script | Run it in the terminal: python calculator.py | app | C-s2-empty, C-s2-unsaved, C-s2-wrong_folder, C-s2-typo, C-s2-terminal_closed, C-s2-right |
| step.started | Write an add function | In calculator.py, type def add(a, b): … | app | C-s3-empty, C-s3-unsaved, C-s3-wrong_folder, C-s3-typo, C-s3-terminal_closed, C-s3-right |
| step.started | Run your first script | Run it in the terminal: python3 calculator.py | app | B-s2-unsaved, B-s2-wrong_folder, B-s2-typo, B-s2-terminal_closed, B-s2-right |
| spotlight |  | Type python3 calculator.py at the terminal prompt, then press Enter | one | B-s2-unsaved, B-s2-wrong_folder, B-s2-typo, B-s2-terminal_closed, B-s2-right |
