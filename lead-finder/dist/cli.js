#!/usr/bin/env node
import { run } from './pipeline.js';
function parseArgs(argv) {
    const args = {};
    for (let i = 0; i < argv.length; i++) {
        const arg = argv[i];
        const next = argv[i + 1];
        switch (arg) {
            case '--ciudad':
            case '--city':
                args.city = next;
                i++;
                break;
            case '--sector':
                args.sector = next;
                i++;
                break;
            case '--max':
                args.maxResults = parseInt(next, 10);
                i++;
                break;
            case '--max-audits':
                args.maxAudits = parseInt(next, 10);
                i++;
                break;
            case '--include-seen':
                args.includeSeen = true;
                break;
            case '--out':
                args.outPath = next;
                i++;
                break;
        }
    }
    return args;
}
const args = parseArgs(process.argv.slice(2));
if (!args.city || !args.sector) {
    console.error(`Usage: npm start -- --city "Madrid" --sector "dentists" [options]

Options:
  --max N            Maximum businesses to scrape (default: config.json)
  --max-audits N     Maximum LLM audits per run (default: 50)
  --include-seen     Include leads exported in previous runs
  --out file         Output path (default: leads.json)`);
    process.exit(1);
}
run({
    city: args.city,
    sector: args.sector,
    maxResults: args.maxResults,
    maxAudits: args.maxAudits,
    includeSeen: args.includeSeen,
    outPath: args.outPath,
}).catch((err) => {
    console.error('Fatal error:', err instanceof Error ? err.message : err);
    process.exit(1);
});
