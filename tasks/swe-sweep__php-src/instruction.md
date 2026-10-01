<role>You are a helpful assistant that can interact with a computer shell to solve programming tasks.</role>

<instructions>
# Task

Your task is to fix all REPOSITORY DISCOVERABLE BUGS in repository given to you.
You MUST NOT make any OUT OF SCOPE edits.

## Definitions

### REPOSITORY

REPOSITORY means anything in the checked out working directory, including code,
and documentation.

### BUG

A bug is a behavior of the software that diverges from EXPECTED BEHAVIOR of it.

### REPOSITORY DISCOVERABLE BUG

A REPOSITORY DISCOVERABLE BUG is a bug whose source of EXPECTED BEHAVIOR is apparent to a reader of the REPOSITORY alone.
For the purposes of this classification, we only allow the ACCEPTED SOURCES OF EXPECTED BEHAVIOR and explicitly exclude any
OUT OF BAND KNOWLEDGE.

### ACCEPTED SOURCES OF EXPECTED BEHAVIOR

#### (1) User-facing documentation

The repository's own statements about itself that can be seen by the user and are therefore
assumed to be expected behavior by any user of the software project.

This includes documentation files and other parts of the repository that are turned into user-facing
documentation artifacts, such as docstrings or type annotations.

The repository may also incorporate an external source by reference, i.e.,
if a module states that it implements a named standard, that standard becomes
an in-repo contract.

Similarly, if in-repo contract sources claim to implement a mathematical function, or
a clearly established scientific concept, the code can be expected to stay true to
the mathematical/scientific expectation.

#### (2) Universally accepted expectations

Universally accepted expectations, e.g.,

- No segmentation faults in a C++ program. Note that other types of exceptions in e.g.,
  python, might be the excpted behavior (e.g., a ValueError in a library)
- No accidental deletion of user data.
- No freezes in a UI.
- No infinite loops.

The threshold for this category should be very high, i.e., you must be absolutely
sure that the expectation is universally shared by any user of this library.

### OUF OF BAND KNOWLEDGE

Knowledge not available from the two sources above.
This includes in particular:

- what the maintainers intended (unless evidenced by in-repo contracts)
- what an issue or PR text asserts,
- what users would want, and your own judgment that the old behavior was undesirable.

Your familiarity with this project from training is out of band.

### PRE-EXISTING TESTS

Pre-existing tests are the tests that are in the repository when you start.

### PRE-EXISTING GREEN TESTS

All PRE-EXISTING TESTS that are passing befor eyou make any edits

## OUT OF SCOPE

### Bugs only

You MUST NOT implement new features, changes, or enhancements.

### No modification to PRE-EXISTING TESTS

Do NOT edit or delete existing tests to make them pass.

### No failing of PRE-EXISTING GREEN TESTS

None of the PRE-EXISTING GREEN TESTS are allowed to be failing because of your changes.
Run the test suite at the beginning of your task and remember which tests are failing.
These are the only (!) PRE-EXISTING TESTS hhat are allowed to fail.
Breaking any (!) other PRE-EXISTING TEST will result in your score being set to zero.
This means that even if you found a clear, repository-evident bug, if fixing it breaks an existing test,
you MUST NOT do it.
Note that this even applies if any `Hint: ` section in the first user message explicitly points out
a bug, or information that points to it.
You must not, and under no circumstances, modify or make a pre-existing green test fail.
Instead, you should simply ignore these kinds of bugs.

## Settings

You are in a container. The REPOSITORY is checked out at `/php-src`.

## Fairplay

This is a large task, but it IS (!) possible to solve.
You need to diligently work over a long time to achieve this task.
You must not break any rule because you deem the task too hard or too big.
If you are found to be breaking any fairplay rule, your score will be set to 0.

The following is considered to be cheating, a violation of fairplay:

- You must discover all bugs and fix them by looking at the source present only. Any way of gaining information about the
  "future" of this code (by looking in the internet, by poking around other installed versions etc.) is not allowed.
- You do not have internet access. You MUST NOT try to gain internet access.
- You MUST NOT attempt to gain access to source code other than the repository that is checked out at `/php-src`.
- You MUST NOT use the size of the task to make excuses for "cheating"
</instructions>

Explore the code, find as many real bugs as you can, and fix them by editing the source files in place.
