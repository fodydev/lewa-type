document.addEventListener("DOMContentLoaded", () => {
    try {
        const af = new AfrimInput({
            textFieldElementID: "textfield",
            downloadStatusElementID: "download-status",
            tooltipElementID: "tooltip",
            tooltipInputElementID: "tooltip-input",
            tooltipPredicatesElementID: "tooltip-predicates",
            configUrl: "https://raw.githubusercontent.com/fodydev/afrim-data/4b177197bb37c9742cd90627b1ad543c32ec791b/gez/gez.toml",
        });
        console.log("✅ Afrim Input initialized successfully.");
        console.log("Afrim Input object:", af);
    } catch (err) {
        console.error("❌ Error initializing Afrim Input:", err);
    }
});
