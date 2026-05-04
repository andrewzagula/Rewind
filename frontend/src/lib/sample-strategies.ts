import rawSampleStrategies from "./sample-strategies.json";

export interface SampleStrategy {
  id: string;
  name: string;
  description: string;
  tags: string[];
  defaultParams: Record<string, number | string | boolean>;
  code: string;
}

export const sampleStrategies = rawSampleStrategies as unknown as SampleStrategy[];
