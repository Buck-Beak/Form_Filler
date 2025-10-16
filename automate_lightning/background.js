// Connect to Python Native Host
const port = chrome.runtime.connectNative('com.autofill.host');

// Example: send current URL and required fields to Python
function requestAutofill(fields) {
    const msg = {
        url: window.location.href,
        telegram_id: "101", // or dynamic user ID from bot
        fields: fields // optional: send placeholder keywords
    };
    port.postMessage(msg);
}

// Receive JSON from Python
port.onMessage.addListener((response) => {
    console.log("Received JSON from Python:", response);

    response.fields.forEach(f => {
        const el = document.querySelector(f.selector);
        if (el) el.value = f.value;
    });
});

// Trigger autofill on page load
window.addEventListener("load", () => {
    // Example: pass expected fields; could parse page dynamically
    const fields = [
        { "selector": "input[name='username']", "keyword": "username" },
        { "selector": "input[name='password']", "keyword": "password" }
    ];
    requestAutofill(fields);
});
