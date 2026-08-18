"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, formulaDefinitions, metricTypes } from "@/lib/api";
import { FORMULA_DEFINITIONS_QUERY_KEY, METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import { FORMULA_INPUT_VARS, type FormulaKey } from "@/lib/types";

const FORMULA_LABELS: Record<FormulaKey, string> = {
  bmi: "BMI",
  body_fat_navy: "Body fat % (Navy method)",
  tdee_mifflin: "TDEE (Mifflin-St Jeor)",
};

export function CreateFormulaDefinitionDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [computedMetricTypeId, setComputedMetricTypeId] = useState("");
  const [formulaKey, setFormulaKey] = useState<FormulaKey>("bmi");
  const [inputMapping, setInputMapping] = useState<Record<string, string>>({});

  const metricTypesQuery = useQuery({
    queryKey: METRIC_TYPES_QUERY_KEY,
    queryFn: () => metricTypes.list(),
  });
  const allTypes = metricTypesQuery.data?.results ?? [];
  const computedTypes = allTypes.filter((type) => type.is_computed);
  const inputTypes = allTypes.filter((type) => !type.is_computed);
  const requiredVars = FORMULA_INPUT_VARS[formulaKey];

  function reset() {
    setComputedMetricTypeId("");
    setFormulaKey("bmi");
    setInputMapping({});
  }

  const mutation = useMutation({
    mutationFn: formulaDefinitions.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FORMULA_DEFINITIONS_QUERY_KEY });
      toast.success("Formula definition created");
      reset();
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to create formula definition");
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!computedMetricTypeId) {
      toast.error("Choose a computed metric type");
      return;
    }
    const mapping: Record<string, number> = {};
    for (const variable of requiredVars) {
      if (inputMapping[variable]) mapping[variable] = Number(inputMapping[variable]);
    }
    mutation.mutate({
      computed_metric_type: Number(computedMetricTypeId),
      formula_key: formulaKey,
      input_mapping: mapping,
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>New formula</Button>} />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>New formula definition</DialogTitle>
            <DialogDescription>
              Wire a computed metric type to a built-in formula and the metric types it reads
              from.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label>Computed metric type</Label>
              <Select
                value={computedMetricTypeId}
                onValueChange={(v) => setComputedMetricTypeId(v ?? "")}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {computedTypes.map((type) => (
                    <SelectItem key={type.id} value={String(type.id)}>
                      {type.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {computedTypes.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Create a metric type with &quot;Computed&quot; enabled first.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Formula</Label>
              <Select
                value={formulaKey}
                onValueChange={(v) => {
                  setFormulaKey(v as FormulaKey);
                  setInputMapping({});
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(FORMULA_LABELS) as FormulaKey[]).map((key) => (
                    <SelectItem key={key} value={key}>
                      {FORMULA_LABELS[key]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {requiredVars.map((variable) => (
              <div className="space-y-2" key={variable}>
                <Label>{variable}</Label>
                <Select
                  value={inputMapping[variable] ?? ""}
                  onValueChange={(v) =>
                    setInputMapping((prev) => ({ ...prev, [variable]: v ?? "" }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select input metric type..." />
                  </SelectTrigger>
                  <SelectContent>
                    {inputTypes.map((type) => (
                      <SelectItem key={type.id} value={String(type.id)}>
                        {type.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
