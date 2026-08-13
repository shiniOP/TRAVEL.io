// ============================================================
// TRAVEL.io — FRONTEND CONTROLLER
// ============================================================

let currentThreadId =
    localStorage.getItem("travel_thread_id") || null;

let latestAnswerMarkdown = "";

let waitingForApproval = false;


// ============================================================
// AGENT LABELS
// ============================================================

const AGENT_LABELS = {
    flight_agent: "✈️ Flight Agent",
    hotel_agent: "🏨 Hotel Agent",
    weather_agent: "🌦️ Weather Agent",
    budget_agent: "💰 Budget Agent",
    itinerary_agent: "🗓️ Itinerary Agent",
    final_agent: "✨ Final Planner"
};


// ============================================================
// DOM HELPERS
// ============================================================

function $(id) {
    return document.getElementById(id);
}


// ============================================================
// QUICK PROMPTS
// ============================================================

function setPrompt(text) {

    const input = $("userInput");

    input.value = text;

    input.focus();

    // Put cursor at the end
    input.setSelectionRange(
        input.value.length,
        input.value.length
    );
}


// ============================================================
// LOADING STATE
// ============================================================

function setLoading(isLoading, mode = "draft") {

    const sendBtn = $("sendBtn");
    const btnText = $("btnText");
    const btnLoader = $("btnLoader");

    const approveBtn = $("approveBtn");
    const reviseBtn = $("reviseBtn");

    if (!sendBtn) return;


    // Disable controls
    sendBtn.disabled = isLoading;

    if (approveBtn) {
        approveBtn.disabled = isLoading;
    }

    if (reviseBtn) {
        reviseBtn.disabled = isLoading;
    }


    // --------------------------------------------------------
    // Draft generation
    // --------------------------------------------------------

    if (isLoading && mode === "draft") {

        btnText.textContent = "Planning...";

        btnText.classList.remove("hidden");

        btnLoader.classList.remove("hidden");

    } else {

        btnText.textContent = "Generate Plan";

        btnText.classList.remove("hidden");

        btnLoader.classList.add("hidden");
    }


    // --------------------------------------------------------
    // Approval loading
    // --------------------------------------------------------

    if (isLoading && mode === "approval") {

        if (approveBtn) {

            approveBtn.dataset.originalText =
                approveBtn.textContent;

            approveBtn.textContent =
                "Processing...";

        }

        if (reviseBtn) {

            reviseBtn.disabled = true;
        }

    } else {

        if (approveBtn) {

            approveBtn.textContent =
                "✓ Approve & Generate Final";
        }

        if (reviseBtn) {

            reviseBtn.textContent =
                "↻ Revise Using Feedback";
        }
    }
}


// ============================================================
// ERROR HANDLING
// ============================================================

function showError(message) {

    const errorBox = $("errorBox");

    if (!errorBox) return;

    errorBox.textContent = `⚠️ ${message}`;

    errorBox.classList.remove("hidden");

    errorBox.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function hideError() {

    const errorBox = $("errorBox");

    if (!errorBox) return;

    errorBox.classList.add("hidden");

    errorBox.textContent = "";
}


// ============================================================
// MARKDOWN RENDERING
// ============================================================

function renderMarkdown(element, markdown) {

    if (!element) return;

    if (
        typeof marked !== "undefined" &&
        typeof marked.parse === "function"
    ) {

        element.innerHTML =
            marked.parse(markdown || "");

    } else {

        element.textContent =
            markdown || "";
    }
}


// ============================================================
// WORKFLOW VISUALIZATION
// ============================================================

function showWorkflow(data) {

    const section =
        $("workflowSection");

    const reasoning =
        $("supervisorReasoning");

    const chips =
        $("agentChips");

    const guardrailBadge =
        $("guardrailBadge");


    if (!section) return;


    // --------------------------------------------------------
    // Supervisor reasoning
    // --------------------------------------------------------

    reasoning.textContent =
        data.supervisor_reasoning ||
        "TRAVEL.io supervisor completed workflow routing.";


    // --------------------------------------------------------
    // Clear old agents
    // --------------------------------------------------------

    chips.innerHTML = "";


    // --------------------------------------------------------
    // Selected agents
    // --------------------------------------------------------

    const selectedAgents =
        data.selected_agents || [];


    selectedAgents.forEach((agent, index) => {

        const chip =
            document.createElement("span");

        chip.className =
            "agent-chip";


        chip.textContent =
            AGENT_LABELS[agent] || agent;


        // Small staggered animation
        chip.style.animationDelay =
            `${index * 80}ms`;


        chips.appendChild(chip);
    });


    // --------------------------------------------------------
    // Guardrail
    // --------------------------------------------------------

    if (data.guardrail_allowed === false) {

        guardrailBadge.textContent =
            "⛔ Guardrail blocked";

        guardrailBadge.classList.add(
            "blocked"
        );

    } else {

        guardrailBadge.textContent =
            "✓ Guardrail passed";

        guardrailBadge.classList.remove(
            "blocked"
        );
    }


    // --------------------------------------------------------
    // Show workflow
    // --------------------------------------------------------

    section.classList.remove("hidden");

    section.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


// ============================================================
// RESULT DISPLAY
// ============================================================

function showResult(
    answer,
    threadId,
    isDraft = false
) {

    latestAnswerMarkdown =
        answer || "";


    const resultSection =
        $("resultSection");

    const resultBox =
        $("resultBox");

    const threadInfo =
        $("threadInfo");

    const resultTitle =
        $("resultTitle");


    if (!resultSection) return;


    // Render AI answer
    renderMarkdown(
        resultBox,
        latestAnswerMarkdown
    );


    // Thread
    threadInfo.textContent =
        `Thread ID: ${threadId || "-"}`;


    // Title
    resultTitle.textContent =
        isDraft
            ? "Draft Travel Plan"
            : "Your Final AI Travel Plan";


    // Show result
    resultSection.classList.remove(
        "hidden"
    );


    // Scroll
    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


// ============================================================
// HUMAN-IN-THE-LOOP
// ============================================================

function showApproval(data) {

    waitingForApproval = true;


    const section =
        $("approvalSection");

    const approvalRequest =
        $("approvalRequest");


    if (!section) return;


    approvalRequest.textContent =
        data.approval_request ||
        "Review the draft and approve it or provide feedback for revision.";


    section.classList.remove(
        "hidden"
    );


    section.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function hideApproval() {

    waitingForApproval = false;


    const section =
        $("approvalSection");

    const feedback =
        $("approvalFeedback");


    if (section) {

        section.classList.add(
            "hidden"
        );
    }


    if (feedback) {

        feedback.value = "";
    }
}


// ============================================================
// SEND TRAVEL REQUEST
// ============================================================

async function sendMessage() {

    hideError();


    // Don't allow another request while HITL is active
    if (waitingForApproval) {

        showError(
            "Please approve or revise the current draft before starting another plan."
        );

        return;
    }


    const input =
        $("userInput");


    const message =
        input.value.trim();


    // --------------------------------------------------------
    // Validation
    // --------------------------------------------------------

    if (!message) {

        showError(
            "Please enter your travel request first."
        );

        input.focus();

        return;
    }


    if (message.length < 5) {

        showError(
            "Please provide a little more detail about your trip."
        );

        input.focus();

        return;
    }


    // --------------------------------------------------------
    // Loading
    // --------------------------------------------------------

    setLoading(
        true,
        "draft"
    );


    try {

        const response =
            await fetch(
                "/api/travel",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        message: message,

                        thread_id:
                            currentThreadId
                    })
                }
            );


        // ----------------------------------------------------
        // Parse response
        // ----------------------------------------------------

        const data =
            await response.json();


        // ----------------------------------------------------
        // Handle HTTP errors
        // ----------------------------------------------------

        if (
            !response.ok ||
            !data.success
        ) {

            throw new Error(
                data.error ||
                "TRAVEL.io could not process your request."
            );
        }


        // ----------------------------------------------------
        // Store thread
        // ----------------------------------------------------

        currentThreadId =
            data.thread_id;


        localStorage.setItem(
            "travel_thread_id",
            currentThreadId
        );


        // ----------------------------------------------------
        // Workflow
        // ----------------------------------------------------

        showWorkflow(data);


        // ----------------------------------------------------
        // HITL required
        // ----------------------------------------------------

        if (data.requires_approval) {

            showResult(
                data.itinerary ||
                data.answer,
                data.thread_id,
                true
            );

            showApproval(data);

        }

        // ----------------------------------------------------
        // Direct final answer
        // ----------------------------------------------------

        else {

            hideApproval();

            showResult(
                data.answer,
                data.thread_id,
                false
            );
        }


        // Clear input after successful request
        input.value = "";


    } catch (error) {

        console.error(
            "TRAVEL.io request error:",
            error
        );

        showError(
            error.message ||
            "Something went wrong while generating your travel plan."
        );

    } finally {

        setLoading(
            false,
            "draft"
        );
    }
}


// ============================================================
// HUMAN APPROVAL / REVISION
// ============================================================

async function submitApproval(
    approved
) {

    hideError();


    // --------------------------------------------------------
    // Validate state
    // --------------------------------------------------------

    if (
        !currentThreadId ||
        !waitingForApproval
    ) {

        showError(
            "There is no draft currently waiting for approval."
        );

        return;
    }


    const feedbackInput =
        $("approvalFeedback");


    const feedback =
        feedbackInput.value.trim();


    // --------------------------------------------------------
    // Revision requires feedback
    // --------------------------------------------------------

    if (
        !approved &&
        !feedback
    ) {

        showError(
            "Please enter revision feedback before requesting changes."
        );

        feedbackInput.focus();

        return;
    }


    setLoading(
        true,
        "approval"
    );


    try {

        const response =
            await fetch(
                "/api/travel/approve",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        thread_id:
                            currentThreadId,

                        approved:
                            approved,

                        feedback:
                            feedback
                    })
                }
            );


        const data =
            await response.json();


        // ----------------------------------------------------
        // Error
        // ----------------------------------------------------

        if (
            !response.ok ||
            !data.success
        ) {

            throw new Error(
                data.error ||
                "Could not resume the travel workflow."
            );
        }


        // ----------------------------------------------------
        // Update thread
        // ----------------------------------------------------

        currentThreadId =
            data.thread_id ||
            currentThreadId;


        localStorage.setItem(
            "travel_thread_id",
            currentThreadId
        );


        // ----------------------------------------------------
        // Show updated workflow
        // ----------------------------------------------------

        showWorkflow(data);


        // ----------------------------------------------------
        // Hide HITL
        // ----------------------------------------------------

        hideApproval();


        // ----------------------------------------------------
        // Show final answer
        // ----------------------------------------------------

        showResult(
            data.answer,
            currentThreadId,
            false
        );


    } catch (error) {

        console.error(
            "TRAVEL.io approval error:",
            error
        );

        showError(
            error.message ||
            "Could not process your approval."
        );

    } finally {

        setLoading(
            false,
            "approval"
        );
    }
}


// ============================================================
// COPY RESULT
// ============================================================

async function copyResult() {

    const resultBox =
        $("resultBox");


    if (!resultBox) return;


    const text =
        resultBox.innerText.trim();


    if (!text) {

        showError(
            "There is no travel plan available to copy."
        );

        return;
    }


    const copyBtn =
        document.querySelector(
            ".copy-btn"
        );


    try {

        await navigator.clipboard.writeText(
            text
        );


        const oldText =
            copyBtn.textContent;


        copyBtn.textContent =
            "✓ Copied";


        copyBtn.classList.add(
            "success"
        );


        setTimeout(() => {

            copyBtn.textContent =
                oldText;

            copyBtn.classList.remove(
                "success"
            );

        }, 1600);


    } catch (error) {

        console.error(
            "Copy error:",
            error
        );

        showError(
            "Could not copy the travel plan."
        );
    }
}


// ============================================================
// DOWNLOAD PDF
// ============================================================

function downloadPDF() {

    const pdfContent =
        $("pdfContent");


    if (
        !latestAnswerMarkdown ||
        !pdfContent
    ) {

        showError(
            "No travel plan available to download."
        );

        return;
    }


    if (
        typeof html2pdf === "undefined"
    ) {

        showError(
            "PDF library could not be loaded."
        );

        return;
    }


    const downloadBtn =
        document.querySelector(
            ".download-btn"
        );


    const oldText =
        downloadBtn.textContent;


    downloadBtn.textContent =
        "Preparing PDF...";


    downloadBtn.disabled =
        true;


    // --------------------------------------------------------
    // PDF options
    // --------------------------------------------------------

    const options = {

        margin: 0.5,

        filename:
            "TRAVEL.io-ai-travel-plan.pdf",

        image: {

            type: "jpeg",

            quality: 0.98
        },

        html2canvas: {

            scale: 2,

            useCORS: true,

            backgroundColor:
                "#ffffff"
        },

        jsPDF: {

            unit: "in",

            format: "a4",

            orientation: "portrait"
        },

        pagebreak: {

            mode: [
                "avoid-all",
                "css",
                "legacy"
            ]
        }
    };


    // --------------------------------------------------------
    // Generate
    // --------------------------------------------------------

    html2pdf()

        .set(options)

        .from(pdfContent)

        .save()

        .then(() => {

            downloadBtn.textContent =
                "✓ PDF Ready";

            setTimeout(() => {

                downloadBtn.textContent =
                    oldText;

                downloadBtn.disabled =
                    false;

            }, 1500);

        })

        .catch((error) => {

            console.error(
                "PDF error:",
                error
            );

            downloadBtn.textContent =
                oldText;

            downloadBtn.disabled =
                false;

            showError(
                "Could not generate the PDF."
            );
        });
}


// ============================================================
// KEYBOARD SHORTCUT
// ============================================================

document.addEventListener(
    "keydown",
    function (event) {

        // Ctrl + Enter
        if (
            event.ctrlKey &&
            event.key === "Enter"
        ) {

            event.preventDefault();

            sendMessage();
        }
    }
);


// ============================================================
// ENTER KEY BEHAVIOR
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const input =
            $("userInput");


        if (!input) return;


        // Ctrl + Enter = submit
        input.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Enter" &&
                    event.ctrlKey
                ) {

                    event.preventDefault();

                    sendMessage();
                }
            }
        );
    }
);


// ============================================================
// RESTORE THREAD
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        if (currentThreadId) {

            console.log(
                "TRAVEL.io thread restored:",
                currentThreadId
            );
        }
    }
);