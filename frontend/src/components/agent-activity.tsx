"use client";

import {
  ArrowRight,
  Check,
  ChevronDown,
  Circle,
  CircleAlert,
  LoaderCircle,
  Wrench,
} from "lucide-react";
import type { Answer, ProgressStep, ToolUsage } from "@/lib/models";

const agents = [
  { id: "retriever", label: "Retriever" },
  { id: "analyst", label: "Analyst" },
  { id: "answer", label: "Answer" },
  { id: "verification", label: "Verification" },
] as const;

function StatusIcon({ status }: { status: string }) {
  if (status === "running")
    return <LoaderCircle size={14} className="activity-spinner" />;
  if (status === "completed") return <Check size={14} />;
  if (status === "failed") return <CircleAlert size={14} />;
  return <Circle size={14} />;
}

export function AgentFlow({ steps }: { steps: ProgressStep[] }) {
  const running = [...steps]
    .reverse()
    .find((step) => step.status === "running");
  return (
    <div className="agent-flow">
      <ol aria-label="Agent progress" className="agent-stages">
        {agents.map((agent, index) => {
          const history = steps.filter((step) => step.agent === agent.id);
          const stage =
            [...history].reverse().find((step) => step.kind === "agent") ??
            history.at(-1);
          const status =
            running?.agent === agent.id
              ? "running"
              : (stage?.status ?? "pending");
          return (
            <li
              key={agent.id}
              data-status={status}
              aria-current={status === "running" ? "step" : undefined}
            >
              <span className="agent-stage-icon">
                <StatusIcon status={status} />
              </span>
              <strong>{agent.label}</strong>
              <small>
                {status === "running"
                  ? "Working"
                  : status === "completed"
                    ? "Done"
                    : status === "failed"
                      ? "Interrupted"
                      : "Waiting"}
              </small>
              {index < agents.length - 1 && (
                <ArrowRight
                  size={12}
                  className="agent-arrow"
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
      <p className="agent-current" role="status" aria-live="polite">
        {running
          ? running.label
          : steps.length
            ? "Finishing this step…"
            : "Preparing agents…"}
      </p>
      <ActivityHistory steps={steps} />
    </div>
  );
}

export function ActivityHistory({ steps }: { steps: ProgressStep[] }) {
  if (!steps.length) return null;
  return (
    <details className="activity-history">
      <summary>
        Agent activity{" "}
        <span>
          {steps.length} {steps.length === 1 ? "step" : "steps"}
        </span>
        <ChevronDown size={14} />
      </summary>
      <ol>
        {steps.map((step) => (
          <li key={step.id} data-status={step.status}>
            <StatusIcon status={step.status} />
            <span>
              <strong>
                {agents.find((agent) => agent.id === step.agent)?.label}
              </strong>
              {step.label}
            </span>
            <small>
              {step.status === "completed"
                ? "Done"
                : step.status === "running"
                  ? "Working"
                  : "Interrupted"}
            </small>
          </li>
        ))}
      </ol>
    </details>
  );
}

const toolLabels: Record<string, string> = {
  calculator: "Calculator",
  table_extractor: "Table extraction",
  document_comparison: "Document comparison",
  data_analysis: "Data analysis",
};

export function ToolsUsed({ answer }: { answer: Answer }) {
  const tools: ToolUsage[] =
    answer.tools_used ??
    Object.values(
      answer.tool_results.reduce<Record<string, ToolUsage>>((items, result) => {
        const tool = items[result.name] ?? {
          name: result.name,
          label: toolLabels[result.name] ?? result.name.replaceAll("_", " "),
          agent: "analyst",
          calls: 0,
          completed: 0,
          failed: 0,
        };
        tool.calls++;
        tool.completed++;
        items[result.name] = tool;
        return items;
      }, {}),
    );
  if (answer.tools_used === undefined && !tools.length) return null;
  return (
    <section className="tools-used" aria-label="Tools used">
      <div className="tools-heading">
        <Wrench size={14} />
        <strong>Tools used</strong>
        <span>{tools.length}</span>
      </div>
      {tools.length ? (
        <ul>
          {tools.map((tool) => (
            <li key={tool.name}>
              <span className="tool-used-icon">
                <Wrench size={14} />
              </span>
              <div>
                <strong>{tool.label}</strong>
                <small>
                  {agents.find((agent) => agent.id === tool.agent)?.label} ·{" "}
                  {tool.calls} {tool.calls === 1 ? "call" : "calls"}
                </small>
              </div>
              <span
                className={
                  tool.failed ? "tool-outcome has-failure" : "tool-outcome"
                }
              >
                {tool.completed > 0 && <span>{tool.completed} completed</span>}
                {tool.failed > 0 && <span>{tool.failed} failed</span>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>No tools were needed for this response.</p>
      )}
      {!!answer.tool_results.length && (
        <details className="tool-details">
          <summary>
            View analysis results
            <ChevronDown size={14} />
          </summary>
          {answer.tool_results.map((tool, index) => (
            <div key={index}>
              <strong>
                {toolLabels[tool.name] ?? tool.name.replaceAll("_", " ")}
              </strong>
              {tool.output.result !== undefined && (
                <p>
                  Result:{" "}
                  <b>
                    {typeof tool.output.result === "object"
                      ? JSON.stringify(tool.output.result)
                      : String(tool.output.result)}
                  </b>
                </p>
              )}
              <details>
                <summary>View recorded output</summary>
                <pre>{JSON.stringify(tool.output, null, 2)}</pre>
              </details>
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
