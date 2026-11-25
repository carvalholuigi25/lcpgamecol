import { View, Text, StyleSheet } from 'react-native';

export default function GamesUpdateScreen() {
  return (
    <View style={styles.container}>
      <Text>Games Update Screen</Text>
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
