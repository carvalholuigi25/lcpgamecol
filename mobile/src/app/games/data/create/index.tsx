import { View, Text, StyleSheet } from 'react-native';

export default function GamesCreateScreen() {
  return (
    <View style={styles.container}>
      <Text>Games Create Screen</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
