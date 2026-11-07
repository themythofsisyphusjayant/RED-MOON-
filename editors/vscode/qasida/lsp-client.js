// Minimal JSON-RPC-over-stdio LSP client (pure Node, no dependencies).
// It speaks exactly the protocol forge.py lsp implements: initialize,
// full-sync didOpen/didChange/didClose, publishDiagnostics, completion,
// shutdown/exit. The VS Code-specific mapping lives in extension.js,
// so this file can be tested headlessly against the real server.
"use strict";

const { spawn } = require("child_process");

function encode(obj) {
  const body = Buffer.from(JSON.stringify(obj), "utf8");
  return Buffer.concat([
    Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, "ascii"),
    body,
  ]);
}

class LspClient {
  constructor(command, handlers) {
    this.command = command;
    this.handlers = handlers || {};
    this.child = null;
    this.buffer = Buffer.alloc(0);
    this.nextId = 1;
    this.pending = new Map();
    this.started = false;
    this.stopping = false;
    this.startError = null;
  }

  start() {
    if (this.started) return Promise.resolve();
    return new Promise((resolve, reject) => {
      let settled = false;
      let child;
      try {
        child = spawn(this.command[0], this.command.slice(1), {
          stdio: ["pipe", "pipe", "pipe"],
        });
      } catch (err) {
        reject(err);
        return;
      }
      this.child = child;
      child.on("error", (err) => {
        this.startError = err;
        if (!settled) {
          settled = true;
          reject(err);
        } else if (this.handlers.onError) {
          this.handlers.onError(err);
        }
      });
      child.on("exit", () => {
        if (!settled) {
          settled = true;
          reject(new Error("language server exited before initialize"));
        } else if (!this.stopping && this.handlers.onError) {
          this.handlers.onError(new Error("language server exited"));
        }
      });
      child.stdout.on("data", (chunk) => this._onData(chunk));
      // stderr is diagnostics for us, never shown to the user.
      if (child.stderr) child.stderr.on("data", () => {});
      this._request("initialize", {
        processId: process.pid,
        rootUri: null,
        capabilities: {
          textDocument: {
            publishDiagnostics: {},
            completion: { completionItem: {} },
          },
        },
        clientInfo: { name: "qasida-vscode", version: "1.0.0" },
      })
        .then(() => {
          this._notify("initialized", {});
          this.started = true;
          settled = true;
          resolve();
        })
        .catch((err) => {
          if (!settled) {
            settled = true;
            reject(err);
          }
        });
    });
  }

  _onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    for (;;) {
      const headerEnd = this.buffer.indexOf("\r\n\r\n");
      if (headerEnd === -1) return;
      const header = this.buffer.slice(0, headerEnd).toString("ascii");
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match) {
        // Unknown framing; drop the header and keep going.
        this.buffer = this.buffer.slice(headerEnd + 4);
        continue;
      }
      const length = parseInt(match[1], 10);
      const bodyStart = headerEnd + 4;
      if (this.buffer.length < bodyStart + length) return;
      const body = this.buffer.slice(bodyStart, bodyStart + length).toString("utf8");
      this.buffer = this.buffer.slice(bodyStart + length);
      let msg;
      try {
        msg = JSON.parse(body);
      } catch {
        continue;
      }
      this._onMessage(msg);
    }
  }

  _onMessage(msg) {
    if (msg.method === "textDocument/publishDiagnostics") {
      if (this.handlers.onDiagnostics) {
        this.handlers.onDiagnostics(msg.params.uri, msg.params.diagnostics || []);
      }
      return;
    }
    if (msg.id !== undefined && this.pending.has(msg.id)) {
      const { resolve, reject } = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message || "server error"));
      else resolve(msg.result);
    }
    // Server requests and unknown notifications are ignored: this
    // server sends none beyond publishDiagnostics.
  }

  _request(method, params) {
    if (!this.child) return Promise.reject(new Error("server not started"));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      try {
        this.child.stdin.write(
          encode({ jsonrpc: "2.0", id, method, params })
        );
      } catch (err) {
        this.pending.delete(id);
        reject(err);
      }
    });
  }

  _notify(method, params) {
    if (!this.child) return;
    try {
      this.child.stdin.write(encode({ jsonrpc: "2.0", method, params }));
    } catch {
      // Server gone; the exit handler reports it.
    }
  }

  didOpen(uri, text) {
    if (this.started) {
      this._notify("textDocument/didOpen", {
        textDocument: { uri, languageId: "qasida", version: 1, text },
      });
    }
  }

  didChange(uri, text) {
    if (this.started) {
      this._notify("textDocument/didChange", {
        textDocument: { uri, version: 1 },
        contentChanges: [{ text }],
      });
    }
  }

  didClose(uri) {
    if (this.started) {
      this._notify("textDocument/didClose", { textDocument: { uri } });
    }
  }

  completion(uri, line, character) {
    if (!this.started) return Promise.resolve([]);
    return this._request("textDocument/completion", {
      textDocument: { uri },
      position: { line, character },
    })
      .then((result) => (result && result.items) || [])
      .catch(() => []);
  }

  stop() {
    if (!this.child) return Promise.resolve();
    this.stopping = true;
    const child = this.child;
    // NOTE: this.child must stay set until shutdown/exit are sent,
    // because _request/_notify no-op once it is null.
    return this._request("shutdown", null)
      .catch(() => {})
      .then(() => {
        this._notify("exit", undefined);
        this.child = null;
        this.started = false;
        try {
          child.stdin.end();
        } catch {}
        return new Promise((resolve) => {
          let done = false;
          const finish = () => {
            if (!done) {
              done = true;
              resolve();
            }
          };
          child.on("exit", finish);
          setTimeout(() => {
            try {
              child.kill();
            } catch {}
            finish();
          }, 1000);
        });
      });
  }
}

module.exports = { LspClient };
