# Qasida — Simple Guide for School Students

Dedicated to Tejaswini — Qasida.
No big words here. If you can use a computer and do class 10 maths,
you can run this language.

## 1. What is a programming language, in simple words?

A programming language is a way to give instructions to a computer.
You write the instructions in a file. The computer reads them and
does the work for you.

Example: you tell the computer "add these numbers" or "print my
name". It does exactly what you wrote. Nothing magic.

Qasida is one such language. It was made to be
safe and simple. Safe means: if you make a mistake, it tells you
clearly, instead of silently giving a wrong answer.

## 2. What do you need before you start?

You need only 3 things:

1. A computer (Windows, Mac, or Linux — any one works).
2. Python 3. Python is a free program. Most computers already
   have it. You can check in step 3 below.
3. A C compiler. This sounds scary, but it is just a small tool
   that turns your program into a real app. On Linux and Mac it
   is usually already there. On Windows, install the free
   "Build Tools for Visual Studio" and tick the C++ box.

You also need internet, one time only, to download the language.

## 3. Steps to run it — do this, then this

### Step 1: Download the language

Open your terminal. Terminal is the black window where you type
commands. On Windows it is called Command Prompt or PowerShell.
On Mac, open Terminal from Applications. On Linux, open Terminal.

Type this, then press Enter:

```sh
git clone https://github.com/jayantt1dubeyy/RED-MOON-
```

This downloads a folder called `RED-MOON-`. That folder is the
language. Its old name was Forge, so inside the folder you will
still see files called `forge.py`. That is normal. The language
name is Qasida, the tool file is still called `forge.py` so
old programs do not break.

### Step 2: Go inside the folder

```sh
cd RED-MOON-
```

`cd` means "change directory". You are now inside the folder.

### Step 3: Check Python and the compiler

Type these two lines, one by one:

```sh
python3 --version
cc --version
```

If both show a version number, you are ready. If Python is not
found, try `python --version` instead of `python3 --version`.
If `cc` is not found, install the C compiler from step 2 above,
then try again.

### Step 4: Run your first program

Type this:

```sh
python3 forge.py run examples/qasida_demo.fg
```

You should see:

```
Qasida
For Teju, my Qasida
Safe. Simple. Natively fast.
```

Well done. You just ran your first Qasida program.

### Step 5: Write your own program

Open a text editor. Not Word — use Notepad, VS Code, or any
plain text editor. Make a new file called `myfirst.fg` and type
this:

```forge
fn main() -> int {
    println("Hello, I am learning Qasida!");
    let marks: int = 85;
    println("My marks =", marks);
    return 0;
}
```

Save the file inside the `RED-MOON-` folder. Then run it:

```sh
python3 forge.py run myfirst.fg
```

You should see:

```
Hello, I am learning Qasida!
My marks = 85
```

### Step 6: What each line means

- `fn main() -> int {` — "start the program here". Every
  program starts with this line.
- `println("...");` — "print this line on the screen".
- `let marks: int = 85;` — "make a box called marks, put
  the number 85 in it". `int` means a whole number.
- `return 0;` — "the program finished well". Every program
  ends with this line.
- `}` — "the program ends here".

### Step 7: Make a real app file (optional, but fun)

If you want a file you can double-click and run, without
typing `python3 forge.py` every time, type:

```sh
python3 forge.py build myfirst.fg -o myfirst
./myfirst
```

Now `myfirst` is a real app made by you.

## 4. Try these ready-made programs

All of these are already in the folder. Just run them:

```sh
python3 forge.py run examples/matrix.fg
# It multiplies two tables of numbers. Output: 58 64 139 154

python3 forge.py run examples/apps/todo.fg -- add "do homework"
python3 forge.py run examples/apps/todo.fg -- list
# A small todo list app. It saves your tasks in todo.txt

python3 forge.py run examples/ml_train_xor.fg
# A tiny AI that learns by itself. It starts with a loss of
# 0.558973 and learns until the loss is 0.000267766
```

## 5. Where is this language used in real life?

Not in big companies yet — it is still new. But the ideas
inside it are used in real life every day. Here is what you
can already build with it, in simple words:

### 1. School tools
- **Marks average calculator:** take 5 subjects, add them,
  divide by 5. You already saw `mean` in this language.
- **Todo list for homework:** the todo app above. Add a task,
  list tasks, mark a task done.
- **Quiz program:** ask a question, read the answer, say
  right or wrong. This uses `if` and `println`.

### 2. Money and shop tools
- **Bill calculator:** price × quantity, add tax, print total.
- **Shop stock list:** keep a list of items and their prices
  in a file, read the file, print the list.

### 3. Small AI and maths tools
- **Predict marks from study hours:** this is called linear
  regression. The program learns a line from old data, then
  guesses the marks for a new number of study hours.
  See `examples/ml_linear_regression.fg`.
- **Learn a pattern:** the XOR program above learns a pattern
  by itself, by trying again and again and fixing its mistakes.
  That is how all AI learning works, just on a much bigger scale.

### 4. Fast tools for computers
- **Count words in a file, sort numbers, search a list:**
  these are the small jobs computers do all day. This language
  is fast at them because it makes a real app, not a slow
  script.

### 5. Learning how computers really work
- The same language can run on a small CPU made from scratch
  (called big32, in simulation) and in a web browser (called
  WASM). That is how students learn what is inside a computer.

## 6. What this language cannot do yet — honestly

- It cannot make games with graphics and buttons yet.
- It cannot make a full website with login and photos yet.
- It cannot train a big AI like ChatGPT. It can train only
  small models, like the XOR example.
- It does not have thousands of ready-made packages yet, like
  Python does.

Knowing what it cannot do is also learning. No language can
do everything.

## 7. If something goes wrong

| Problem | What to do |
|---|---|
| `python3: command not found` | Try `python` instead of `python3`. If that also fails, install Python 3 from python.org. |
| `cc: command not found` | Install a C compiler. On Windows, install Build Tools for Visual Studio. On Mac, install Xcode Command Line Tools. On Linux, install `gcc`. |
| `file not found` | Check you are inside the `RED-MOON-` folder (`cd RED-MOON-`) and the file name is spelled correctly, including `.fg`. |
| `qasida: error: ...` | Read the error line. It tells you the file, line number, and what is wrong — for example, a missing `;` or a wrong type. Fix that line and run again. |

## 8. Your next 3 steps

1. Run the demo in Step 4.
2. Change one line in `myfirst.fg` — change 85 to your own
   marks — and run it again.
3. Try the todo app, then try to make your own marks-average
   program.

That is it. You do not need to read the whole book first.
Write a small program, run it, break it, fix it, run it again.
That is how everyone learns programming.
