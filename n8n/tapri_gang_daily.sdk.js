import { workflow, node, trigger, ifElse, expr, sticky, newCredential } from '@n8n/workflow-sdk';

const auth = { httpTemplatedCustomAuth: newCredential('Tapri Gang API') };
const authParams = { authentication: 'genericCredentialType', genericAuthType: 'httpTemplatedCustomAuth' };

const daily = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.3,
  config: {
    name: 'Daily 10:00',
    parameters: { rule: { interval: [{ field: 'cronExpression', expression: '0 10 * * *' }] } }
  }
});

const cfg = node({
  type: 'n8n-nodes-base.set',
  version: 3.4,
  config: {
    name: 'Config',
    parameters: {
      mode: 'manual',
      includeOtherFields: false,
      assignments: {
        assignments: [
          { id: 'api', name: 'api', value: 'https://YOUR-TUNNEL.trycloudflare.com', type: 'string' },
          { id: 'privacy', name: 'privacy', value: 'private', type: 'string' },
          { id: 'publish_at', name: 'publish_at', value: expr('{{ $now.setZone("Asia/Kolkata").set({ hour: 19, minute: 30, second: 0, millisecond: 0 }).toISO() }}'), type: 'string' }
        ]
      }
    }
  }
});

const make = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.3,
  config: {
    name: 'Make Episode',
    parameters: { ...authParams, method: 'POST', url: expr('{{ $("Config").item.json.api }}/api/make'), sendBody: true, specifyBody: 'json', jsonBody: '{}' },
    credentials: auth
  }
});

const waitRender = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: { name: 'Wait For Render', parameters: { amount: 4, unit: 'minutes' } }
});

const getTicket = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.3,
  config: {
    name: 'Check Ticket',
    parameters: { ...authParams, method: 'GET', url: expr('{{ $("Config").item.json.api }}/api/job?id={{ $("Make Episode").item.json.ticket }}') },
    credentials: auth
  }
});

const isDone = ifElse({
  version: 2.2,
  config: {
    name: 'Video Ready?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' },
        conditions: [{ leftValue: expr('{{ $json.status }}'), operator: { type: 'string', operation: 'equals' }, rightValue: 'done' }],
        combinator: 'and'
      }
    }
  }
});

const isFailed = ifElse({
  version: 2.2,
  config: {
    name: 'Failed?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict' },
        conditions: [{ leftValue: expr('{{ $json.status }}'), operator: { type: 'string', operation: 'equals' }, rightValue: 'failed' }],
        combinator: 'and'
      }
    }
  }
});

const waitMore = node({
  type: 'n8n-nodes-base.wait',
  version: 1.1,
  config: { name: 'Wait 2 Min', parameters: { amount: 2, unit: 'minutes' } }
});

const stopFail = node({
  type: 'n8n-nodes-base.stopAndError',
  version: 1,
  config: { name: 'Stop: Render Failed', parameters: { errorMessage: expr('Tapri Gang render failed: {{ $json.error }}') } }
});

const approve = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.3,
  config: {
    name: 'Upload Scheduled',
    parameters: {
      ...authParams,
      method: 'POST',
      url: expr('{{ $("Config").item.json.api }}/api/approve'),
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ JSON.stringify({ job_id: $json.job_id, privacy: $("Config").item.json.privacy, publish_at: $("Config").item.json.publish_at }) }}')
    },
    credentials: auth
  }
});

const note = sticky('## Tapri Gang daily\nDrives the local factory API (python main.py api) through a Cloudflare tunnel.\n1. Credential "Tapri Gang API": headers template Authorization = Bearer {{api_key}}, api_key = FACTORY_API_TOKEN from .env.\n2. Set api (tunnel URL) in Config.\n3. Make Episode -> poll -> upload scheduled for 19:30 IST.\nKeep inactive until a manual test run works.', [daily, cfg, make], { color: 4 });

export default workflow('tapri-gang-daily', 'Tapri Gang - Daily Episode')
  .add(daily)
  .to(cfg)
  .to(make)
  .to(waitRender)
  .to(getTicket)
  .to(isDone
    .onTrue(approve)
    .onFalse(isFailed
      .onTrue(stopFail)
      .onFalse(waitMore.to(getTicket))));
