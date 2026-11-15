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
| A | s1 | unsaved | FAIL | stayed open | Start · Add the add function; Stuck on this step? |
| A | s1 | wrong_folder | FAIL | stayed open | Start · Add the add function; Stuck on this step? |
| A | s1 | typo | FAIL | stayed open | Start: Add the add function; Start · Add the add function; Stuck on this step? |
| A | s1 | terminal_closed | FAIL | stayed open | Start: Add the add function; Start · Add the add function; Stuck on this step? |
| A | s1 | right | FAIL | did NOT pass with the right code | Start: Add the add function; Start · Add the add function; Stuck on this step? |
| A | s2 | empty | FAIL | stayed open | Question · Run your first output; Where to work; Stuck on this step? |
| A | s2 | unsaved | FAIL | passed before the file was saved | (no card) |
| A | s2 | wrong_folder | FAIL | passed on code in another folder | (no card) |
| A | s2 | typo | FAIL | stayed open | Start: Run your first output; Start · Run your first output; Stuck on this step? |
| A | s2 | terminal_closed | FAIL | passed without running the program | (no card) |
| A | s2 | right | PASS | passed | (no card) |
| A | s3 | empty | FAIL | stayed open | Start · Add three more operations; Where to work; Stuck on this step? |
| A | s3 | unsaved | FAIL | passed before the file was saved | (no card) |
| A | s3 | wrong_folder | FAIL | stayed open | Start · Add three more operations; Stuck on this step? |
| A | s3 | typo | FAIL | stayed open | Start: Add three more operations; Start · Add three more operations; Stuck on this step? |
| A | s3 | terminal_closed | PASS | passed (code saved; no terminal needed) | (no card) |
| A | s3 | right | PASS | passed | (no card) |
| B | s1 | empty | FAIL | stayed open | Start · Create the project file; Where to work; Stuck on this step? |
| B | s1 | unsaved | FAIL | passed before the file was saved | (no card) |
| B | s1 | wrong_folder | FAIL | passed on code in another folder | (no card) |
| B | s1 | typo | FAIL | stayed open | Start: Create the project file; Start · Create the project file; Where to work; Stuck on this step? |
| B | s1 | terminal_closed | PASS | passed (code saved; no terminal needed) | (no card) |
| B | s1 | right | PASS | passed | (no card) |
| B | s2 | empty | FAIL | stayed open | Start · Create the project file; Where to work; Stuck on this step? |
| B | s2 | unsaved | FAIL | stayed open | Start · Run your first script; Stuck on this step? |
| B | s2 | wrong_folder | FAIL | stayed open | Start · Run your first script; Stuck on this step? |
| B | s2 | typo | FAIL | stayed open | Start: Run your first script; Start · Run your first script; Stuck on this step? |
| B | s2 | terminal_closed | FAIL | stayed open (not run yet) | Start: Run your first script; Start · Run your first script; Stuck on this step? |
| B | s2 | right | FAIL | did NOT pass with the right code | Start: Run your first script; Start · Run your first script; Stuck on this step? |
| B | s3 | empty | FAIL | stayed open | Start · Add the math functions; Where to work; Stuck on this step? |
| B | s3 | unsaved | FAIL | stayed open | Start · Add the math functions; Stuck on this step? |
| B | s3 | wrong_folder | FAIL | stayed open | Start · Add the math functions; Stuck on this step? |
| B | s3 | typo | FAIL | stayed open | Start: Add the math functions; Start · Add the math functions; Stuck on this step? |
| B | s3 | terminal_closed | FAIL | stayed open | Start: Add the math functions; Start · Add the math functions; Stuck on this step? |
| B | s3 | right | FAIL | did NOT pass with the right code | Start: Add the math functions; Start · Add the math functions; Stuck on this step? |
| C | s1 | empty | FAIL | stayed open | Start · Print a welcome message; Stuck on this step? |
| C | s1 | unsaved | FAIL | passed before the file was saved | (no card) |
| C | s1 | wrong_folder | FAIL | passed on code in another folder | (no card) |
| C | s1 | typo | FAIL | stayed open | Start: Print a welcome message; Start · Print a welcome message; Stuck on this step? |
| C | s1 | terminal_closed | PASS | passed (code saved; no terminal needed) | (no card) |
| C | s1 | right | PASS | passed | (no card) |
| C | s2 | empty | FAIL | stayed open | Start · Run your script; Stuck on this step? |
| C | s2 | unsaved | FAIL | stayed open | Start · Run your script; Stuck on this step? |
| C | s2 | wrong_folder | FAIL | stayed open | Start · Run your script; Stuck on this step? |
| C | s2 | typo | FAIL | stayed open | Start: Run your script; Start · Run your script; Stuck on this step? |
| C | s2 | terminal_closed | FAIL | stayed open (not run yet) | Start: Run your script; Start · Run your script; Stuck on this step? |
| C | s2 | right | FAIL | did NOT pass with the right code | Start: Run your script; Start · Run your script; Stuck on this step? |
| C | s3 | empty | FAIL | stayed open | Start · Write an add function; Stuck on this step? |
| C | s3 | unsaved | FAIL | stayed open | Start · Write an add function; Stuck on this step? |
| C | s3 | wrong_folder | FAIL | stayed open | Start · Write an add function; Stuck on this step? |
| C | s3 | typo | FAIL | stayed open | Start: Write an add function; Start · Write an add function; Stuck on this step? |
| C | s3 | terminal_closed | FAIL | stayed open | Start: Write an add function; Start · Write an add function; Stuck on this step? |
| C | s3 | right | FAIL | did NOT pass with the right code | Start: Write an add function; Start · Write an add function; Stuck on this step? |

### Failing card texts (unique)

| source | title | body | rules broken | seen in |
|---|---|---|---|---|
| card | Stuck on this step? | Skip it, or ask for a hint. | app, file, one | A-s1-empty, A-s1-unsaved, A-s1-wrong_folder, A-s1-typo, A-s1-terminal_closed, A-s1-right (+33) |
| card | Start · Add the math functions | Replace the print line with four functions: add(a, b), subtract(a, b), multiply(a, b) and divide(a, b), each returning the result. Make divide return "Error: divide by zero" when b == 0, then add print(add(2, 3)) and print(divide(8, 0)) at the bottom to test. | app, file, one, words | B-s3-empty, B-s3-unsaved, B-s3-wrong_folder, B-s3-typo, B-s3-terminal_closed, B-s3-right |
| card | Start · Run your script | In the VS Code terminal, run python calculator.py (or python3 calculator.py on Mac/Linux) and check that Simple Calculator appears. | one, words | C-s2-empty, C-s2-unsaved, C-s2-wrong_folder, C-s2-typo, C-s2-terminal_closed, C-s2-right |
| card | Start · Write an add function | In calculator.py, above the print line, define def add(a, b): that returns a + b, then add print(add(2, 3)) at the bottom. | app, one, words | C-s3-empty, C-s3-unsaved, C-s3-wrong_folder, C-s3-typo, C-s3-terminal_closed, C-s3-right |
| card | Start · Add the add function | In calculator.py, below the comment, write def add(a, b): that returns a + b, then add print(add(2, 3)) at the bottom. | app, one, words | A-s1-unsaved, A-s1-wrong_folder, A-s1-typo, A-s1-terminal_closed, A-s1-right |
| card | Start · Run your first script | In the terminal, run: python3 calculator.py. You should see Calculator ready printed. | app | B-s2-unsaved, B-s2-wrong_folder, B-s2-typo, B-s2-terminal_closed, B-s2-right |
| card | Start: Add the add function | In calculator.py, below the comment, write def add(a, b): that returns a + b, then add print(add(2, 3)) at the bottom. | app, one, words | A-s1-typo, A-s1-terminal_closed, A-s1-right |
| card | Start · Add three more operations | In calculator.py, above the print line, write subtract, multiply and divide functions that each take a and b and return the result. | app, words | A-s3-empty, A-s3-wrong_folder, A-s3-typo |
| card | Start · Create the project file | Create calculator.py in the lesson folder, then type: print("Calculator ready"). | app, one | B-s1-empty, B-s1-typo, B-s2-empty |
| card | Where to work | Create calculator.py in the lesson folder | app | B-s1-empty, B-s1-typo, B-s2-empty |
| card | Start: Run your first script | In the terminal, run: python3 calculator.py. You should see Calculator ready printed. | app | B-s2-typo, B-s2-terminal_closed, B-s2-right |
| card | Start: Add the math functions | Replace the print line with four functions: add(a, b), subtract(a, b), multiply(a, b) and divide(a, b), each returning the result. | app, file, one, words | B-s3-typo, B-s3-terminal_closed, B-s3-right |
| card | Start: Run your script | In the VS Code terminal, run python calculator.py (or python3 calculator.py on Mac/Linux) and check that Simple Calculator appears. | one, words | C-s2-typo, C-s2-terminal_closed, C-s2-right |
| card | Start: Write an add function | In calculator.py, above the print line, define def add(a, b): that returns a + b, then add print(add(2, 3)) at the bottom. | app, one, words | C-s3-typo, C-s3-terminal_closed, C-s3-right |
| card | Start · Print a welcome message | In calculator.py, add the line print("Simple Calculator") at the bottom, then save the file. | app, one, words | C-s1-empty, C-s1-typo |
| card | Question · Add the add function | Does your output show “add function is written in the” yet? If not, what step produces it? | app, file, label, words | A-s1-empty |
| card | Question · Run your first output | Does your output show “The add function is still in” yet? If not, what step produces it? | app, file, label, words | A-s2-empty |
| card | Start: Run your first output | In the terminal, run python calculator.py and check that it prints 5. | app, one | A-s2-typo |
| card | Start · Run your first output | In the terminal, run python calculator.py and check that it prints 5. | app, one | A-s2-typo |
| card | Start: Add three more operations | In calculator.py, above the print line, write subtract, multiply and divide functions that each take a and b and return the result. | app, words | A-s3-typo |
| card | Start: Create the project file | Create calculator.py in the lesson folder, then type: print("Calculator ready"). | app, one | B-s1-typo |
| card | Start: Print a welcome message | In calculator.py, add the line print("Simple Calculator") at the bottom, then save the file. | app, one, words | C-s1-typo |

### Step action lines and spotlight captions that break a rule

| source | title | body | rules broken | seen in |
|---|---|---|---|---|
| step.started | Create the project file | In calculator.py, type print("Calculator ready") | app | B-s1-empty, B-s1-unsaved, B-s1-wrong_folder, B-s1-typo, B-s1-terminal_closed, B-s1-right (+1) |
| step.started | Add the add function | In calculator.py, type def add(a, b): … | app | A-s1-empty, A-s1-unsaved, A-s1-wrong_folder, A-s1-typo, A-s1-terminal_closed, A-s1-right |
| step.started | Run your first output | In calculator.py, type print(add(2, 3)) | app | A-s2-empty, A-s2-unsaved, A-s2-wrong_folder, A-s2-typo, A-s2-terminal_closed, A-s2-right |
| step.started | Add three more operations | In calculator.py, type def subtract(a, b): … | app | A-s3-empty, A-s3-unsaved, A-s3-wrong_folder, A-s3-typo, A-s3-terminal_closed, A-s3-right |
| step.started | Add the math functions | In calculator.py, type def add(a, b): … | app | B-s3-empty, B-s3-unsaved, B-s3-wrong_folder, B-s3-typo, B-s3-terminal_closed, B-s3-right |
| step.started | Print a welcome message | In calculator.py, type print("Simple Calculator") | app | C-s1-empty, C-s1-unsaved, C-s1-wrong_folder, C-s1-typo, C-s1-terminal_closed, C-s1-right |
| step.started | Run your script | In (terminal), type python calculator.py | app | C-s2-empty, C-s2-unsaved, C-s2-wrong_folder, C-s2-typo, C-s2-terminal_closed, C-s2-right |
| spotlight |  | Type this in the VS Code terminal (use python3 on Mac/Linux if python isn't found), then press Enter | one, words | C-s2-empty, C-s2-unsaved, C-s2-wrong_folder, C-s2-typo, C-s2-terminal_closed, C-s2-right |
| step.started | Write an add function | In calculator.py, type def add(a, b): … | app | C-s3-empty, C-s3-unsaved, C-s3-wrong_folder, C-s3-typo, C-s3-terminal_closed, C-s3-right |
| step.started | Run your first script | In (terminal), type python3 calculator.py | app | B-s2-unsaved, B-s2-wrong_folder, B-s2-typo, B-s2-terminal_closed, B-s2-right |
| spotlight |  | Type python3 calculator.py at the terminal prompt, then press Enter | one | B-s2-unsaved, B-s2-wrong_folder, B-s2-typo, B-s2-terminal_closed, B-s2-right |
