// Qasida — VS Code extension host.
// Thin VS Code layer only: documents, diagnostics, completion and
// commands. The wire protocol lives in lsp-client.js (dependency-free,
// headlessly testable against forge.py lsp).
"use strict";

const vscode = require("vscode");
const { LspClient } = require("./lsp-client");

// LSP CompletionItemKind -> VS Code CompletionItemKind.
const KIND_MAP = { 3: 2, 14: 13, 22: 21 };

let client = null;
let diagnostics = null;
let serverWarned = false;

function serverCommand() {
  const cfg = vscode.workspace.getConfiguration("qasida");
  const cmd = cfg.get("serverCommand", ["qasida", "lsp"]);
  return Array.isArray(cmd) && cmd.length > 0 ? cmd : ["qasida", "lsp"];
}

function executable() {
  return vscode.workspace.getConfiguration("qasida").get("executable", "qasida");
}

function startServer() {
  if (client) return client.start().catch(() => {});
  client = new LspClient(serverCommand(), {
    onDiagnostics: (uri, diags) => {
      if (!diagnostics) return;
      diagnostics.set(
        vscode.Uri.parse(uri),
        diags.map((d) => {
          const range = new vscode.Range(
            d.range.start.line,
            d.range.start.character,
            d.range.end.line,
            d.range.end.character
          );
          const severity =
            d.severity === 1
              ? vscode.DiagnosticSeverity.Error
              : vscode.DiagnosticSeverity.Warning;
          const diag = new vscode.Diagnostic(range, d.message, severity);
          diag.source = d.source || "qasida";
          return diag;
        })
      );
    },
    onError: () => {
      if (serverWarned) return;
      serverWarned = true;
      vscode.window.showWarningMessage(
        "Qasida language server is not running (is the `qasida` command installed? See the extension README). Run / Check / Format still work from the terminal once it is."
      );
    },
  });
  return client.start().catch(() => {
    if (!serverWarned) {
      serverWarned = true;
      vscode.window.showWarningMessage(
        "Qasida language server could not start (is the `qasida` command installed? See the extension README). Run / Check / Format still work from the terminal once it is."
      );
    }
  });
}

function openDocs() {
  if (!client) return;
  for (const doc of vscode.workspace.textDocuments) {
    if (doc.languageId === "qasida") client.didOpen(doc.uri.toString(), doc.getText());
  }
}

function runInTerminal(command) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "qasida") {
    vscode.window.showWarningMessage("Open a Qasida (.fg) file first.");
    return;
  }
  const file = editor.document.fileName;
  editor.document.save().then(() => {
    const terminal = vscode.window.createTerminal("Qasida");
    terminal.show();
    terminal.sendText(`${command} "${file}"`);
  });
}

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection("qasida");
  context.subscriptions.push(diagnostics);

  startServer().then(openDocs);

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId === "qasida" && client) {
        client.didOpen(doc.uri.toString(), doc.getText());
      }
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId === "qasida" && client) {
        client.didChange(event.document.uri.toString(), event.document.getText());
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      if (doc.languageId === "qasida" && client) {
        client.didClose(doc.uri.toString());
        diagnostics.delete(doc.uri);
      }
    }),
    vscode.languages.registerCompletionItemProvider(
      "qasida",
      {
        provideCompletionItems(document, position) {
          if (!client) return [];
          return client
            .completion(document.uri.toString(), position.line, position.character)
            .then((items) =>
              items.map((item) => {
                const ci = new vscode.CompletionItem(
                  item.label,
                  KIND_MAP[item.kind] !== undefined
                    ? KIND_MAP[item.kind]
                    : vscode.CompletionItemKind.Text
                );
                if (item.detail) ci.detail = item.detail;
                return ci;
              })
            );
        },
      },
      "."
    ),
    vscode.commands.registerCommand("qasida.runFile", () =>
      runInTerminal(`${executable()} run`)
    ),
    vscode.commands.registerCommand("qasida.checkFile", () =>
      runInTerminal(`${executable()} check`)
    ),
    vscode.commands.registerCommand("qasida.formatFile", () =>
      runInTerminal(`${executable()} fmt`)
    ),
    vscode.commands.registerCommand("qasida.buildFile", () =>
      runInTerminal(`${executable()} build`)
    ),
    vscode.commands.registerCommand("qasida.restartServer", () => {
      const old = client;
      client = null;
      serverWarned = false;
      const restart = old ? old.stop() : Promise.resolve();
      restart.then(() => startServer().then(openDocs));
    })
  );
}

function deactivate() {
  if (client) return client.stop();
  return undefined;
}

module.exports = { activate, deactivate };
