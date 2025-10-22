<script setup lang="ts">
interface Props {
  id: number,
  name: string,
  type: string,
  x: number,
  y: number
}

defineProps<Props>()
</script>
<template>
  <li class="object-item">
    {{ name }} ({{ type }}) - [{{ x }}, {{ y }}]
  </li>
</template>