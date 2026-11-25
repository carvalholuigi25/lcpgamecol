import { View, Text, StyleSheet } from 'react-native';

export default function AdminMainScreen() {
  return (
    <View style={styles.container}>
      <Text>Admin Main Screen</Text>
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
