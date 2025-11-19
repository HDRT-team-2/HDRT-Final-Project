<script setup lang="ts">
interface Column {
  key: string;
  label: string;
  align?: 'left' | 'center' | 'right';
  width?: string;
}

interface Props {
  columns: Column[];
  data: Record<string, any>[];
  striped?: boolean;
  bordered?: boolean;
  hover?: boolean;
  size?: 'sm' | 'md' | 'lg';
  maxHeight?: string;
}

const props = withDefaults(defineProps<Props>(), {
  striped: true,
  bordered: true,
  hover: true,
  size: 'sm',
  maxHeight: undefined
});

const getSizeClass = () => {
  switch (props.size) {
    case 'sm': return 'text-xs';
    case 'md': return 'text-sm';
    case 'lg': return 'text-base';
    default: return 'text-xs';
  }
};

const getAlignClass = (align?: string) => {
  switch (align) {
    case 'center': return 'text-center';
    case 'right': return 'text-right';
    default: return 'text-left';
  }
};
</script>

<template>
  <div class="h-full overflow-auto" :style="maxHeight ? { maxHeight } : {}">
    <table class="w-full" :class="getSizeClass()">
      <!-- Header -->
      <thead class="sticky top-0 z-10">
        <tr class="bg-rotem-100 rounded-lg">
          <th
            v-for="(column, idx) in columns"
            :key="column.key"
            class="py-1 text-xs font-bold"
            :class="[
              getAlignClass(column.align),
              {
                'rounded-l-lg': idx === 0,
                'rounded-r-lg': idx === columns.length - 1
              }
            ]"
            :style="column.width ? { width: column.width } : {}"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      
      <!-- Body -->
      <tbody>
        <tr
          v-for="(row, index) in data"
          :key="index"
          :class="{
            'bg-rotem-100': striped && index % 2 === 1,
            'hover:bg-rotem-100': hover,
            'border-b border-rotem-100': bordered && index < data.length - 1
          }"
          class="transition-colors"
        >
          <td
            v-for="column in columns"
            :key="column.key"
            class="py-1"
            :class="getAlignClass(column.align)"
          >
            <slot 
              :name="column.key" 
              :row="row" 
              :value="row[column.key]" 
              :index="index"
            >
              {{ row[column.key] }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
    
    <!-- Empty state -->
    <div 
      v-if="data.length === 0"
      class="text-center py-8 text-gray-500"
      :class="getSizeClass()"
    >
      <slot name="empty">
        데이터가 없습니다.
      </slot>
    </div>
  </div>
</template>