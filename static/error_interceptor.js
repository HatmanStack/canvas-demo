// Store the original console.error function so we can still use it
const originalConsoleError = console.error;

// Create a flag to ensure the reload only happens once
let hasReloaded = false;

// Override the default console.error function
console.error = function(...args) {
    // 1. Pass the error to the original function to maintain normal browser behavior.
    originalConsoleError.apply(console, args);

    // 2. Check if the error message contains our target phrase.
    // We combine all arguments passed to console.error into a single string.
    const errorMessage = args.join(' ').toLowerCase();

    if (!hasReloaded && errorMessage.includes('connection errored out')) {

        // 3. If it's our target error and we haven't reloaded yet, set the flag and reload.
        hasReloaded = true;
        console.log('Gradio "Connection errored out" detected. Forcing refresh.');

        // Use a tiny delay to ensure the error log completes before the page reloads.
        setTimeout(() => {
            location.reload();
        }, 100);
    }
};
