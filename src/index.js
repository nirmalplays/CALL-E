"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const calle_1 = require("@call-e/calle");
// IMPORTANT: Set CALLE_API_KEY environment variable before running
const apiKey = process.env.CALLE_API_KEY;
if (!apiKey) {
    console.error("Error: CALLE_API_KEY environment variable is missing.");
    process.exit(1);
}
const client = new calle_1.CalleClient({ apiKey });
async function main() {
    console.log("Creating call task...");
    // Example: Create a call and wait for its completion. 
    // Replace <E164_PHONE> with a real phone number like +15550123456
    const call = await client.calls.createAndWait({
        task: "Call <E164_PHONE> and confirm whether they can attend Friday lunch.",
        resultSchema: {
            type: "object",
            required: ["can_attend"],
            properties: {
                can_attend: { type: "string", enum: ["yes", "no", "unknown"] },
            },
        },
    });
    console.log("Call Status:", call.status);
    console.log("Task Completed:", call.taskCompleted);
    console.log("Completion Confidence:", call.completionConfidence);
    console.log("Structured Result:", call.structuredResult);
    console.log("Evidence:", call.evidence);
}
main().catch(console.error);
//# sourceMappingURL=index.js.map