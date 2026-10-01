import http from 'k6/http';
import { check } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://127.0.0.1:8765';
const readPaths = [
  { name: 'health', path: '/health' },
  { name: 'dataset_status', path: '/v1/dataset-status' },
  { name: 'trade_stats', path: '/v1/trade-stats?dataset_kind=synthetic' },
  { name: 'coverage', path: '/v1/coverage?country=GBR&flow=X&measure=value' },
  { name: 'sources', path: '/v1/sources' },
];

export const options = {
  scenarios: {
    read_paths: {
      executor: 'constant-vus',
      vus: 8,
      duration: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{endpoint:health}': ['p(95)<20'],
    'http_req_duration{endpoint:dataset_status}': ['p(95)<20'],
    'http_req_duration{endpoint:trade_stats}': ['p(95)<20'],
    'http_req_duration{endpoint:coverage}': ['p(95)<20'],
    'http_req_duration{endpoint:sources}': ['p(95)<20'],
  },
};

export default function () {
  const target = readPaths[__ITER % readPaths.length];
  const response = http.get(baseUrl + target.path, {
    tags: { endpoint: target.name },
  });
  check(response, {
    'read path returns 200': (result) => result.status === 200,
  });
}
