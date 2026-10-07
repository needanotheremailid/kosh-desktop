'use strict';
// Fixed offline bridge; neither style XML nor metadata is evaluated as code.
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const CSL = require(path.join(root, 'vendor', 'csl', 'citeproc.js'));
const MAX_BYTES = 8000000;
let bytes = 0;
const chunks = [];
process.stdin.on('data', chunk => {
  bytes += chunk.length;
  if (bytes > MAX_BYTES) process.exit(1);
  chunks.push(chunk);
});
process.stdin.on('end', () => {
  try {
    const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const items = new Map(request.items.map(item => [String(item.id), item]));
    const engine = new CSL.Engine({
      retrieveLocale: language => {
        if (Object.prototype.hasOwnProperty.call(request.locales, language)) return request.locales[language];
        // Missing variants remain absent; citeproc's documented locale resolution
        // may use a base locale. The selected locale itself is validated in Python.
        return false;
      },
      retrieveItem: id => {
        if (!items.has(String(id))) throw new Error('Unknown item');
        return items.get(String(id));
      }
    }, request.style_xml, request.language, true);
    engine.setOutputFormat('html');
    engine.updateItems([...items.keys()]);
    const citations = [];
    const preceding = [];
    for (let index = 0; index < request.clusters.length; index += 1) {
      const citationID = 'cluster' + index;
      const citation = {citationID, citationItems: request.clusters[index].map(id => ({id: String(id)})),
        properties: {noteIndex: engine.opt.xclass === 'note' ? index + 1 : 0}};
      const update = engine.processCitationCluster(citation, preceding, []);
      for (const [position, rendered] of update[1]) citations[position] = rendered;
      preceding.push([citationID, citation.properties.noteIndex]);
    }
    const bibliography = engine.makeBibliography();
    const result = {citations, references: bibliography ? bibliography[1] : [],
      bibliography_ids: bibliography ? bibliography[0].entry_ids.map(ids => String(ids[0])) : [],
      item_numbers: Object.fromEntries([...items.keys()].map(id => [id, engine.registry.registry[id].seq])),
      citation_format: request.citation_format, style_class: engine.opt.xclass, language: request.language};
    const output = JSON.stringify(result);
    if (Buffer.byteLength(output, 'utf8') > MAX_BYTES) throw new Error('Output limit');
    process.stdout.write(output);
  } catch (_) {
    // Do not emit private metadata or raw parser diagnostics to logs.
    process.stderr.write('CSL request failed.\n');
    process.exitCode = 1;
  }
});
