document.addEventListener('DOMContentLoaded', () => {
    const cy = cytoscape({
        container: document.getElementById('cy'),
        style: [
            {
                selector: 'node',
                style: {
                    'shape': 'round-rectangle',
                    'background-color': '#161b22',
                    'border-width': 1,
                    'border-color': '#30363d',
                    'label': 'data(label)',
                    'color': '#c9d1d9',
                    'font-family': 'JetBrains Mono',
                    'font-size': '10px',
                    'text-valign': 'center',
                    'width': '120px',
                    'height': '60px',
                    'text-wrap': 'wrap',
                    'text-max-width': '100px'
                }
            },
            {
                selector: 'node[type="SUMMARY"]',
                style: {
                    'border-color': '#ff9d00',
                    'background-color': 'rgba(255, 157, 0, 0.05)',
                    'color': '#ff9d00'
                }
            },
            {
                selector: 'node[type="RAW"]',
                style: {
                    'border-color': '#58a6ff',
                    'border-style': 'dashed',
                    'height': '40px'
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#30363d',
                    'target-arrow-color': '#30363d',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'line-style': 'solid'
                }
            },
            {
                selector: 'edge[style="dashed"]',
                style: {
                    'line-style': 'dashed',
                    'opacity': 0.5
                }
            }
        ],
        layout: { name: 'breadthfirst', directed: true, padding: 20 }
    });

    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const chatHistory = document.getElementById('chat-history');
    const loading = document.getElementById('loading');
    const contextList = document.getElementById('active-context');

    async function updateState() {
        try {
            const res = await fetch('/api/state');
            const data = await res.json();

            // Update Header Statistics
            const percent = Math.round((data.token_usage / data.token_limit) * 100);
            document.getElementById('token-progress').style.width = `${percent}%`;
            document.getElementById('token-usage').textContent = data.token_usage.toLocaleString();
            document.getElementById('token-limit').textContent = data.token_limit.toLocaleString();
            document.getElementById('token-percent').textContent = `${percent}%`;
            document.getElementById('node-count').textContent = `${data.summaries.length + data.active_nodes.length} nodes`;

            // Update Active Context Cards
            contextList.innerHTML = '';

            // Render Summaries
            data.summaries.forEach(s => {
                const card = document.createElement('div');
                card.className = 'summary-card';
                card.innerHTML = `
                    <div class="card-header">
                        <span>SUMMARY • DEPTH ${s.depth} • ${s.id}</span>
                        <span>${s.tokens} tok</span>
                    </div>
                    <div class="card-content">${s.content}</div>
                `;
                contextList.appendChild(card);
            });

            // Update DAG Visualization
            cy.elements().remove();

            // Add Summary Nodes
            data.summaries.forEach(s => {
                cy.add({
                    group: 'nodes',
                    data: {
                        id: s.id,
                        label: `SUMMARY D${s.depth}\n${s.tokens} tok`,
                        type: 'SUMMARY'
                    }
                });
            });

            // Add Relationships (Edges)
            data.summaries.forEach(s => {
                if (s.child_ids) {
                    s.child_ids.forEach(childId => {
                        cy.add({
                            group: 'edges',
                            data: { source: s.id, target: childId }
                        });
                    });
                }
            });

            cy.layout({ name: 'breadthfirst', directed: true, padding: 30 }).run();

        } catch (err) { console.error("Failed to update state:", err); }
    }

    async function sendQuery() {
        const query = userInput.value.trim();
        if (!query) return;

        userInput.value = '';
        appendMessage('user', query);
        loading.classList.remove('hidden');

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            const data = await res.json();
            appendMessage('assistant', data.response);
        } catch (err) {
            appendMessage('assistant', "Lỗi kết nối server: " + err);
        } finally {
            loading.classList.add('hidden');
            updateState();
        }
    }

    function appendMessage(role, text) {
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role}`;
        bubble.textContent = text;
        chatHistory.appendChild(bubble);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    sendBtn.addEventListener('click', sendQuery);
    userInput.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') sendQuery();
    });

    // Initial load and periodic refresh
    updateState();
    setInterval(updateState, 10000);
});
