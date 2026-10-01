import { useState } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Plus, X, LayoutGrid } from "lucide-react";
import clsx from "clsx";

function SortablePill({ id, label, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        "flex items-center gap-1.5 pl-1.5 pr-2 py-1.5 rounded-lg border bg-accent-soft border-accent/30 text-accent select-none",
        isDragging && "shadow-panel-lg"
      )}
    >
      <button
        type="button"
        className="cursor-grab active:cursor-grabbing text-accent/70 hover:text-accent"
        {...attributes}
        {...listeners}
        aria-label={`Drag to reorder ${label}`}
      >
        <GripVertical size={14} />
      </button>
      <span className="text-xs font-semibold whitespace-nowrap">{label}</span>
      <button
        type="button"
        onClick={() => onRemove(id)}
        className="text-accent/60 hover:text-negative transition-colors"
        aria-label={`Remove ${label}`}
      >
        <X size={13} />
      </button>
    </div>
  );
}

/**
 * dimensions: [{column, label}]  -- full catalog, discovered from the schema
 * value: [column, ...]           -- selected, in order
 * onChange: (nextValue) => void
 */
export default function DimensionPicker({ dimensions = [], value = [], onChange }) {
  const [addOpen, setAddOpen] = useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const byColumn = Object.fromEntries(dimensions.map((d) => [d.column, d]));
  const available = dimensions.filter((d) => !value.includes(d.column));

  function handleDragEnd(event) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = value.indexOf(active.id);
    const newIndex = value.indexOf(over.id);
    onChange(arrayMove(value, oldIndex, newIndex));
  }

  function addDimension(col) {
    onChange([...value, col]);
    setAddOpen(false);
  }

  function removeDimension(col) {
    onChange(value.filter((c) => c !== col));
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted mr-1">
        <LayoutGrid size={13} />
        Row hierarchy
      </span>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={value} strategy={horizontalListSortingStrategy}>
          <div className="flex flex-wrap items-center gap-2">
            {value.map((col) => (
              <SortablePill
                key={col}
                id={col}
                label={byColumn[col]?.label || col}
                onRemove={removeDimension}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="relative">
        <button
          type="button"
          onClick={() => setAddOpen((v) => !v)}
          disabled={available.length === 0}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-dashed border-border-strong text-xs font-medium text-text-secondary hover:text-accent hover:border-accent/50 transition-colors disabled:opacity-40"
        >
          <Plus size={13} />
          Add dimension
        </button>
        {addOpen && available.length > 0 && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setAddOpen(false)} />
            <div className="absolute z-20 mt-1 left-0 min-w-[180px] bg-card border border-border rounded-lg shadow-panel-lg py-1 animate-fadeIn">
              {available.map((d) => (
                <button
                  key={d.column}
                  type="button"
                  onClick={() => addDimension(d.column)}
                  className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-card-hover transition-colors"
                >
                  {d.label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      {value.length === 0 && (
        <span className="text-xs text-text-muted italic">
          No dimensions selected — showing grand total only
        </span>
      )}
    </div>
  );
}
