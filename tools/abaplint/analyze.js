#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { Config, Expressions, MemoryFile, Nodes, Registry } = require("@abaplint/core");
const corePackage = require("@abaplint/core/package.json");

const PARSER = "abaplint";
const LANGUAGE = "abap";
const VERSION = corePackage.version || "unknown";
const SUFFIXES = new Set([".abap", ".abapinclude"]);

const KIND_BY_TYPE = Object.freeze({
  Report: "abap_program",
  Program: "abap_program",
  ClassDefinition: "abap_class",
  ClassImplementation: "abap_class",
  MethodDef: "abap_method",
  MethodImplementation: "abap_method",
  Form: "abap_form",
  FunctionModule: "abap_function_module",
  CallFunction: "abap_call",
  CallMethod: "abap_call",
  Call: "abap_call",
  Perform: "abap_call",
  Select: "abap_sql",
  Insert: "abap_sql",
  InsertDatabase: "abap_sql",
  Update: "abap_sql",
  UpdateDatabase: "abap_sql",
  Delete: "abap_sql",
  DeleteDatabase: "abap_sql",
  Modify: "abap_sql",
  ModifyDatabase: "abap_sql",
  Types: "abap_type",
  Type: "abap_type",
  Data: "abap_data",
  Parameters: "abap_parameter",
  Parameter: "abap_parameter",
  Include: "abap_include",
});

const SQL_SYMBOL = Object.freeze({
  Select: "SELECT",
  Insert: "INSERT",
  InsertDatabase: "INSERT",
  Update: "UPDATE",
  UpdateDatabase: "UPDATE",
  Delete: "DELETE",
  DeleteDatabase: "DELETE",
  Modify: "MODIFY",
  ModifyDatabase: "MODIFY",
});

const KNOWN_OBJECT_TYPES = new Set([
  "prog", "clas", "intf", "fugr", "incl", "tabl", "view", "ddls", "doma",
  "dtel", "msag", "tran", "cinc", "wapa", "spro", "xinx", "enho", "enhs",
  "sush", "smim", "vvtr", "ttyp", "sqlq", "nrob", "pinf", "sajc", "sfs",
  "sfbs", "stcs", "wdyn", "wdyc", "wdyv", "bdef", "ddlx", "coca", "dcls",
]);

function nodeType(node) {
  try {
    return node.get().constructor.name;
  } catch (_error) {
    return node.constructor.name;
  }
}

function safeGet(object, method, fallback) {
  try {
    return object && typeof object[method] === "function" ? object[method]() : fallback;
  } catch (_error) {
    return fallback;
  }
}

function tokenText(token) {
  try {
    return token.getStr();
  } catch (_error) {
    return "";
  }
}

function statementTokens(statement) {
  try {
    return statement.getTokens().map(tokenText);
  } catch (_error) {
    return [];
  }
}

function expressionText(statement, name) {
  try {
    const expression = statement.findFirstExpression(Expressions[name]);
    return expression ? expression.concatTokens().trim() : "";
  } catch (_error) {
    return "";
  }
}

function unquote(text) {
  if (text.length >= 2) {
    const first = text[0];
    const last = text[text.length - 1];
    if ((first === "'" && last === "'") ||
        (first === '"' && last === '"') ||
        (first === "`" && last === "`")) {
      return text.slice(1, -1);
    }
  }
  return text;
}

function lastMethodSegment(target) {
  let result = target.split("->").pop() || "";
  result = result.split("=>").pop() || "";
  result = result.split("(")[0];
  return result.trim();
}

function statementSymbol(statement, type, tokens) {
  switch (type) {
    case "Report":
    case "Program":
      return expressionText(statement, "ReportName") || tokens[1] || "";
    case "ClassDefinition":
    case "ClassImplementation":
      return expressionText(statement, "ClassName") || tokens[1] || "";
    case "MethodDef":
    case "MethodImplementation":
      return expressionText(statement, "MethodName") || tokens[1] || "";
    case "Form":
      return expressionText(statement, "FormName") || tokens[1] || "";
    case "FunctionModule":
      return expressionText(statement, "Field") || tokens[1] || "";
    case "CallFunction":
      return unquote(expressionText(statement, "FunctionName") || tokens[2] || "");
    case "Call": {
      const target = expressionText(statement, "MethodSource");
      return target ? lastMethodSegment(target) : lastMethodSegment(tokens.slice(2).join(""));
    }
    case "Perform":
      return expressionText(statement, "FormName") || tokens[1] || "";
    case "Type":
    case "Types":
      return expressionText(statement, "NamespaceSimpleName") || tokens[1] || "";
    case "Data": {
      const definition = expressionText(statement, "DefinitionName");
      if (definition) {
        return definition;
      }
      return tokens[1] === "(" ? (tokens[2] || "") : (tokens[1] || "");
    }
    case "Parameter":
    case "Parameters":
      return expressionText(statement, "FieldSub") ||
        expressionText(statement, "ParameterName") || tokens[1] || "";
    case "Include":
      return expressionText(statement, "IncludeName") || tokens[1] || "";
    default:
      return SQL_SYMBOL[type] || "";
  }
}

function statementTarget(statement, type, symbol) {
  switch (type) {
    case "CallFunction":
      return symbol;
    case "Call":
      return expressionText(statement, "MethodSource") || symbol;
    case "Perform":
      return expressionText(statement, "FormName") || symbol;
    default:
      return "";
  }
}

function statementTable(statement, type) {
  if (!(type in SQL_SYMBOL)) {
    return "";
  }
  return expressionText(statement, "DatabaseTable");
}

function nodeRow(node) {
  try {
    if (typeof node.getStart === "function") {
      return node.getStart().getRow();
    }
    return node.getFirstToken().getStart().getRow();
  } catch (_error) {
    return 0;
  }
}

function enrichFile(abapFile) {
  const statements = [];
  let currentClass = "";
  let currentMethod = "";
  let currentForm = "";
  let currentFunction = "";

  for (const statement of abapFile.getStatements()) {
    const type = nodeType(statement);
    const tokens = statementTokens(statement);
    const symbol = statementSymbol(statement, type, tokens);
    const line = nodeRow(statement);
    const endLine = safeGet(statement, "getEnd", null) ?
      statement.getEnd().getRow() : line;

    if (type === "ClassDefinition" || type === "ClassImplementation") {
      currentClass = symbol;
      currentMethod = "";
    } else if (type === "EndClass") {
      currentClass = "";
      currentMethod = "";
      currentForm = "";
      currentFunction = "";
    } else if (type === "MethodImplementation") {
      currentMethod = symbol;
    } else if (type === "EndMethod") {
      currentMethod = "";
    } else if (type === "Form") {
      currentForm = symbol;
    } else if (type === "EndForm") {
      currentForm = "";
    } else if (type === "FunctionModule") {
      currentFunction = symbol;
    } else if (type === "EndFunction") {
      currentFunction = "";
    }

    let owner = "";
    if (currentClass) {
      owner = currentMethod ? `${currentClass}.${currentMethod}` : currentClass;
    } else if (currentFunction) {
      owner = currentFunction;
    } else if (currentForm) {
      owner = currentForm;
    }

    statements.push({
      type,
      kind: KIND_BY_TYPE[type] || null,
      line,
      end_line: endLine,
      tokens,
      symbol,
      owner,
      target: statementTarget(statement, type, symbol),
      table: statementTable(statement, type),
    });
  }
  return statements;
}

function compactStructure(node) {
  if (!node) {
    return null;
  }
  const type = nodeType(node);
  if (node instanceof Nodes.StatementNode) {
    return { type, line: nodeRow(node) };
  }
  if (node instanceof Nodes.StructureNode) {
    const children = [];
    for (const child of safeGet(node, "getChildren", [])) {
      const compact = compactStructure(child);
      if (compact) {
        children.push(compact);
      }
    }
    return { type, line: nodeRow(node), children };
  }
  return null;
}

function objectFiles(object) {
  const files = [];
  const seen = new Set();
  const add = (file) => {
    if (!file) {
      return;
    }
    const filename = safeGet(file, "getFilename", "");
    if (filename && !seen.has(filename)) {
      seen.add(filename);
      files.push(file);
    }
  };

  for (const file of safeGet(object, "getSequencedFiles", [])) {
    add(file);
  }
  if (files.length === 0) {
    for (const file of safeGet(object, "getABAPFiles", [])) {
      add(file);
    }
  }
  return files;
}

function issueRecord(issue, fallbackKey) {
  return {
    key: safeGet(issue, "getKey", fallbackKey),
    message: safeGet(issue, "getMessage", ""),
    line: safeGet(issue, "getStart", null) ? issue.getStart().getRow() : 0,
  };
}

function dedupeErrors(errors) {
  const seen = new Set();
  const unique = [];
  for (const error of errors) {
    const key = `${error.key}|${error.line}|${error.message}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(error);
    }
  }
  return unique.sort((a, b) =>
    (a.line - b.line) || String(a.key).localeCompare(String(b.key)) ||
    String(a.message).localeCompare(String(b.message)));
}

function readText(file) {
  const buffer = fs.readFileSync(file);
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    return text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text;
  } catch (_error) {
    try {
      return new TextDecoder("windows-1252").decode(buffer);
    } catch (_error2) {
      return buffer.toString("latin1");
    }
  }
}

function sanitizeName(name) {
  let result = "";
  for (const character of name) {
    const code = character.charCodeAt(0);
    if ((code >= 48 && code <= 57) || (code >= 65 && code <= 90) ||
        (code >= 97 && code <= 122) || character === "_" || character === "/") {
      result += character;
    } else {
      result += "_";
    }
  }
  return result || "zmeridian";
}

function memoryFilename(file) {
  const base = path.basename(file);
  const parts = base.split(".");
  if (parts.length >= 3 && KNOWN_OBJECT_TYPES.has(parts[1].toLowerCase())) {
    return base;
  }
  return `${sanitizeName(parts[0])}.prog.abap`;
}

function analyze(file) {
  const result = {
    file: path.resolve(file),
    status: "ok",
    parser: PARSER,
    parser_version: VERSION,
    language: LANGUAGE,
    objects: [],
    statements: [],
    structure: null,
    errors: [],
  };

  const suffix = path.extname(file).toLowerCase();
  if (!SUFFIXES.has(suffix)) {
    result.status = "unsupported";
    result.errors.push({
      key: "unsupported", message: "extension non prise en charge", line: 0,
    });
    return result;
  }

  let raw;
  try {
    raw = readText(file);
  } catch (error) {
    result.status = "error";
    result.errors.push({
      key: "read_error", message: String(error.message || error), line: 0,
    });
    return result;
  }

  try {
    const registry = new Registry(Config.getDefault());
    registry.addFile(new MemoryFile(memoryFilename(file), raw));
    registry.parse();

    const objects = Array.from(registry.getObjects());
    const seenFiles = new Set();

    for (const object of objects) {
      const objectType = safeGet(object, "getType", "");
      const objectName = safeGet(object, "getName", "");
      result.objects.push({ type: objectType, name: objectName });

      for (const issue of safeGet(object, "getParsingIssues", [])) {
        result.errors.push(issueRecord(issue, "parser_error"));
      }

      for (const abapFile of objectFiles(object)) {
        const filename = safeGet(abapFile, "getFilename", "");
        if (seenFiles.has(filename)) {
          continue;
        }
        seenFiles.add(filename);

        result.statements.push(...enrichFile(abapFile));
        if (result.structure === null) {
          result.structure = compactStructure(abapFile.getStructure());
        }

        for (const statement of safeGet(abapFile, "getStatements", [])) {
          const type = nodeType(statement);
          if (type === "Unknown" || type === "MacroRecursion") {
            const tokens = statementTokens(statement);
            result.errors.push({
              key: "parser_error",
              message: `Instruction non reconnue : ${tokens[0] || ""}`.trim(),
              line: nodeRow(statement),
            });
          }
        }
      }
    }

    if (objects.length === 0) {
      result.status = "partial";
      result.errors.push({
        key: "no_object",
        message: "abaplint n'a reconnu aucun objet ABAP dans le fichier",
        line: 0,
      });
    }

    if (result.errors.length > 0 && result.status === "ok") {
      result.status = "partial";
    }
  } catch (error) {
    result.status = "error";
    result.errors.push({
      key: "analysis_error", message: String(error.message || error), line: 0,
    });
  }

  result.errors = dedupeErrors(result.errors);
  return result;
}

function main(argv) {
  if (argv.length !== 1) {
    process.stderr.write("usage: node tools/abaplint/analyze.js <fichier.abap>\n");
    process.exitCode = 2;
    return;
  }
  const result = analyze(argv[0]);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exitCode = result.status === "error" ? 1 : 0;
}

if (require.main === module) {
  main(process.argv.slice(2));
}

module.exports = { analyze };
