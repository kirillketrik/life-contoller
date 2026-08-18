"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ApiError, metricTypes } from "@/lib/api";
import { METRIC_TYPES_QUERY_KEY } from "@/lib/query-keys";
import { type Aggregation, createMetricTypeSchema, type ValueType } from "@/lib/types";

export function CreateMetricTypeDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("");
  const [valueType, setValueType] = useState<ValueType>("number");
  const [aggregation, setAggregation] = useState<Aggregation>("");
  const [isComputed, setIsComputed] = useState(false);

  function reset() {
    setName("");
    setUnit("");
    setValueType("number");
    setAggregation("");
    setIsComputed(false);
  }

  const mutation = useMutation({
    mutationFn: metricTypes.create,
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: METRIC_TYPES_QUERY_KEY });
      toast.success(`Created metric type "${created.name}"`);
      reset();
      setOpen(false);
    },
    onError: (error) => {
      toast.error(error instanceof ApiError ? error.message : "Failed to create metric type");
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsed = createMetricTypeSchema.safeParse({
      name,
      unit,
      value_type: valueType,
      aggregation,
      is_computed: isComputed,
    });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Invalid input");
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>New metric type</Button>} />
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>New metric type</DialogTitle>
            <DialogDescription>
              Define a kind of value that can be logged, e.g. &quot;Weight&quot; or &quot;Insulin
              dose&quot;.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="mt-name">Name</Label>
              <Input id="mt-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mt-unit">Unit</Label>
              <Input
                id="mt-unit"
                placeholder="e.g. kg, mg/dL, ml"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Value type</Label>
              <Select value={valueType} onValueChange={(v) => setValueType(v as ValueType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="number">Number</SelectItem>
                  <SelectItem value="text">Text</SelectItem>
                  <SelectItem value="boolean">Boolean</SelectItem>
                  <SelectItem value="date">Date</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Aggregation (optional)</Label>
              <Select
                value={aggregation || "none"}
                onValueChange={(v) => setAggregation(v === "none" ? "" : (v as Aggregation))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="sum">Sum</SelectItem>
                  <SelectItem value="last">Last</SelectItem>
                  <SelectItem value="avg">Average</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="mt-computed">Computed</Label>
                <p className="text-xs text-muted-foreground">
                  Derived from other metrics via a formula (BMI, TDEE, ...) instead of logged
                  directly.
                </p>
              </div>
              <Switch id="mt-computed" checked={isComputed} onCheckedChange={setIsComputed} />
            </div>
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
