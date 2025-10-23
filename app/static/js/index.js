"use strict";

// Simple SSE client helper for competition live updates
function connectCompetitionSSE(compId, onMessage) {
    const url = `/competitions/${compId}/live`;
    const es = new EventSource(url);
    es.onmessage = (ev) => {
        try {
            const data = JSON.parse(ev.data);
            onMessage(data);
        } catch (e) {
            console.error('Invalid SSE data', e);
        }
    };
    es.onerror = (err) => {
        console.error('SSE error', err);
    };
    return es;
}