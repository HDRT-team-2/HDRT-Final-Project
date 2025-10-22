<script setup lang="ts">
interface Props {
  name: string
}

defineProps<Props>()
</script>
<template>
  <li class="object-item">
    {{ name }}
  </li>
</template>