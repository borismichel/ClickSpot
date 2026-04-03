import type { SchemaResponse, QueryResponse } from "../types/api";

export interface ViewProps {
  schema: SchemaResponse;
  selections: Record<string, string[]>;
  queryData: QueryResponse | undefined;
  queryLoading: boolean;
}
