# Contributing to Cut To:

Thanks for helping. Writers, testers and coders are all welcome.

## Reporting a bug

[Open an issue](https://github.com/manojsriharsha-git/cut-to/issues/new/choose) and pick **Bug report**. The most useful reports include:
- the steps that make it happen, e.g. "press Ctrl+1, Ctrl+2, Ctrl+3, then Ctrl+4";
- what you expected, and what happened instead;
- your Cut To: version (**Help → About**) and your Windows version;
- if you can, a small `.cut` or `.fdx` file that shows the problem.

## Suggesting a feature

Open an issue and pick **Feature request**. Tell us what you're trying to do as a writer, not only the button you'd like: that often leads to a better design.

## Contributing code

1. **Fork and branch.** Fork the repository and create a branch, e.g. `fix/ctrl4-crash` or `feature/dual-dialogue`.
2. **Set up.** Follow [docs/BUILDING.md](docs/BUILDING.md).
3. **Keep it small.** Change only what your fix or feature needs.
4. **Test it.** Add a test in `tests/` that fails without your change, and make sure everything passes:
   ```
   python -m pytest
   ```
5. **Follow the code style:**
   - Logic goes in `app/core` (no Qt); windows and widgets go in `app/ui`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
   - Write docstrings and comments in plain language: say what something is for.
   - Keep the user interface quiet and consistent. All colours come from `app/ui/theme.py`.
6. **Open a pull request.** Say what it changes and why. The tests run automatically on GitHub.

By contributing, you agree that your contribution is licensed under the project's licence, [GPL-3.0-or-later](LICENSE).

## Ideas waiting for someone

- Side-by-side dual dialogue (it currently shows one speech under the other).
- Giving (MORE) / (CONT'D) a line of their own.
- A macOS build.
- Translations of the interface.
- Real-time collaboration.
