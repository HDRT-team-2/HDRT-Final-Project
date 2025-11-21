<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import FireLogTable from '@/components/sidebar/FireLogTable.vue'
import { storeToRefs } from 'pinia'
import { useFireStore } from '@/stores/fire-store'
import { computed } from 'vue'

// Fire Store 연결
const fireStore = useFireStore()
const { fires } = storeToRefs(fireStore)
</script>

<template>
  <Card title="사격 이력">
    <FireLogTable :fires="fires" />
  </Card>
</template>