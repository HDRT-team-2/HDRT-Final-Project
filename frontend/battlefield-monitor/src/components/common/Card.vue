<script setup lang="ts">
defineProps<{ title: string }>()

</script>
<template>
  <div>
    <div class="card-header">{{ title }}</div>
    <div class="card-body"><slot /></div>
  </div>

</template>